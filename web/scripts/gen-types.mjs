/**
 * Generate TypeScript types from the JSON Schemas in `contracts/`.
 *
 * Contract: `docs/05_Schema.md` §15 — generated types are never edited by hand and
 * CI fails when `npm --prefix web run gen:types` produces a diff.
 *
 * Deliberately dependency-free: it supports exactly the JSON Schema 2020-12 subset
 * the contracts use (object/array/enum/const/oneOf/anyOf/$ref/$defs/properties),
 * so the generator cannot drift with a third-party upgrade.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CONTRACTS_DIR = join(HERE, "..", "..", "contracts");
const OUT_DIR = join(HERE, "..", "src", "types", "generated");

/** [module name, schema file] — order only affects the barrel file. */
const SCHEMAS = [
  ["sop", "sop.schema.json"],
  ["tracks", "tracks.schema.json"],
  ["timeline", "timeline.schema.json"],
  ["alignment", "alignment.schema.json"],
  ["report", "report.schema.json"],
  ["manifest", "manifest.schema.json"],
  ["review", "review.schema.json"],
  ["thresholds", "thresholds.schema.json"],
];

/** schema $id -> { module, rootName }, filled before generation so refs resolve. */
const ID_TO_MODULE = new Map();

const pascal = (value) =>
  String(value)
    .replace(/[^A-Za-z0-9]+/g, " ")
    .trim()
    .split(/\s+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");

const safeKey = (key) => (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(key) ? key : JSON.stringify(key));

function literalUnion(values) {
  return values.map((value) => JSON.stringify(value)).join(" | ");
}

function typeOf(schema, ctx) {
  if (!schema || typeof schema !== "object") return "unknown";

  if (Array.isArray(schema.oneOf) || Array.isArray(schema.anyOf)) {
    const variants = schema.oneOf ?? schema.anyOf;
    const rendered = variants.map((variant) => typeOf(variant, ctx));
    return [...new Set(rendered)].join(" | ");
  }

  if (typeof schema.$ref === "string") {
    const ref = schema.$ref;
    if (ref.startsWith("#/$defs/")) {
      const key = ref.slice("#/$defs/".length);
      const definition = ctx.defs?.[key];
      // Primitive $defs (semver, sha256, run_id, ...) are inlined instead of
      // exported, so the barrel file cannot re-export colliding aliases.
      if (definition && definition.type !== "object" && !definition.properties) {
        return typeOf(definition, ctx);
      }
      return pascal(key);
    }
    const target = ID_TO_MODULE.get(ref);
    if (!target) throw new Error(`unresolved external $ref in generator: ${ref}`);
    ctx.imports.add(`import type { ${target.rootName} } from "./${target.module}";`);
    return target.rootName;
  }

  if (Object.prototype.hasOwnProperty.call(schema, "const")) {
    return JSON.stringify(schema.const);
  }

  if (Array.isArray(schema.enum)) {
    return literalUnion(schema.enum);
  }

  const declared = schema.type;
  if (Array.isArray(declared)) {
    const rendered = declared.map((entry) => typeOf({ ...schema, type: entry }, ctx));
    return [...new Set(rendered)].join(" | ");
  }

  switch (declared) {
    case "null":
      return "null";
    case "boolean":
      return "boolean";
    case "integer":
    case "number":
      return "number";
    case "string":
      return "string";
    case "array": {
      const item = typeOf(schema.items ?? {}, ctx);
      return item.includes("|") ? `Array<${item}>` : `${item}[]`;
    }
    case "object": {
      const properties = schema.properties;
      if (properties && typeof properties === "object" && Object.keys(properties).length > 0) {
        const required = new Set(schema.required ?? []);
        const fields = Object.entries(properties).map(([key, value]) => {
          const optional = required.has(key) ? "" : "?";
          return `${safeKey(key)}${optional}: ${typeOf(value, ctx)};`;
        });
        return `{ ${fields.join(" ")} }`;
      }
      const additional = schema.additionalProperties;
      if (additional && typeof additional === "object") {
        return `Record<string, ${typeOf(additional, ctx)}>`;
      }
      return "Record<string, unknown>";
    }
    default:
      return "unknown";
  }
}

function emitInterface(name, schema, ctx) {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const lines = Object.entries(properties).map(([key, value]) => {
    const optional = required.has(key) ? "" : "?";
    return `  ${safeKey(key)}${optional}: ${typeOf(value, ctx)};`;
  });
  return `export interface ${name} {\n${lines.join("\n")}\n}`;
}

function generate(module, schema, file) {
  const rootName = pascal(schema.title ?? module);
  const defs = schema.$defs ?? {};
  const ctx = { imports: new Set(), defs };
  const blocks = [];

  for (const [key, value] of Object.entries(defs)) {
    if (value && typeof value === "object" && value.type === "object") {
      blocks.push(emitInterface(pascal(key), value, ctx));
    }
    // Primitive $defs are inlined at each use site (see typeOf), so they are not
    // exported and cannot collide across modules in the barrel file.
  }

  if (Array.isArray(schema.oneOf) || Array.isArray(schema.anyOf)) {
    blocks.push(`export type ${rootName} = ${typeOf(schema, ctx)};`);
  } else if (schema.type === "object" || schema.properties) {
    blocks.push(emitInterface(rootName, schema, ctx));
  } else {
    blocks.push(`export type ${rootName} = ${typeOf(schema, ctx)};`);
  }

  const header = [
    "/**",
    ` * Generated from contracts/${file} by web/scripts/gen-types.mjs — do not edit.`,
    " * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).",
    " */",
    "",
  ].join("\n");

  const imports = [...ctx.imports].sort().join("\n");
  return `${header}${imports ? `${imports}\n\n` : ""}${blocks.join("\n\n")}\n`;
}

function main() {
  const loaded = SCHEMAS.map(([module, file]) => {
    const schema = JSON.parse(readFileSync(join(CONTRACTS_DIR, file), "utf8"));
    return { module, file, schema };
  });

  // Pass 1: register every $id so cross-file $refs resolve regardless of order.
  for (const { module, schema } of loaded) {
    ID_TO_MODULE.set(schema.$id, { module, rootName: pascal(schema.title ?? module) });
  }

  // Pass 2: emit one module per schema plus the barrel.
  mkdirSync(OUT_DIR, { recursive: true });
  const exports = [];
  for (const { module, file, schema } of loaded) {
    writeFileSync(join(OUT_DIR, `${module}.ts`), generate(module, schema, file), "utf8");
    exports.push(`export * from "./${module}";`);
  }
  writeFileSync(
    join(OUT_DIR, "index.ts"),
    ["/** Generated barrel file — do not edit. */", ...exports, ""].join("\n"),
    "utf8",
  );
  console.log(
    `[gen:types] wrote ${loaded.length} schema modules + index.ts into web/src/types/generated`,
  );
}

main();
