import { describe, expect, it } from "vitest";

import tokensCss from "./tokens.css?raw";

/**
 * Token contract (T-6.7, 03_UI_Spec.md §2–§4).
 *
 * jsdom cannot compute layout or colours, so the accessibility promise is pinned to
 * the tokens themselves: exact spec hex values, WCAG contrast ratios computed for
 * every foreground/background pair the UI actually uses, and the type/motion rules
 * that make the app projector-ready.
 */
function token(name: string): string {
  const match = new RegExp(`--${name}:\\s*([^;]+);`).exec(tokensCss);
  if (!match) throw new Error(`token --${name} is not defined in tokens.css`);
  return match[1]!.trim();
}

function rgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(value)) throw new Error(`not a 6-digit hex colour: ${hex}`);
  return [
    parseInt(value.slice(0, 2), 16),
    parseInt(value.slice(2, 4), 16),
    parseInt(value.slice(4, 6), 16),
  ];
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  const [lighter, darker] = a > b ? [a, b] : [b, a];
  return (lighter + 0.05) / (darker + 0.05);
}

const SURFACE = token("surface");

describe("colour tokens", () => {
  it("pins the exact spec values", () => {
    expect(token("bg")).toBe("#0b0f14");
    expect(token("surface")).toBe("#121923");
    expect(token("text")).toBe("#e6edf3");
    expect(token("accent")).toBe("#6ea8ff");
    expect(token("focus")).toBe("#6ea8ff");
  });

  it.each([
    ["text"],
    ["text-muted"],
    ["accent"],
    ["ok"],
    ["error"],
    ["dev-missed"],
    ["dev-order"],
    ["dev-tool"],
    ["needs-review"],
    ["illustration"],
  ])("--%s meets WCAG AA (4.5:1) on the surface", (name) => {
    expect(contrast(token(name), SURFACE)).toBeGreaterThanOrEqual(4.5);
  });

  it("accent ink meets AA on an accent fill", () => {
    expect(contrast(token("accent-ink"), token("accent"))).toBeGreaterThanOrEqual(4.5);
  });

  it("interactive borders meet the 3:1 non-text contrast rule", () => {
    expect(contrast(token("border-strong"), SURFACE)).toBeGreaterThanOrEqual(3);
  });
});

describe("type and motion tokens", () => {
  it("uses an 18 px base with nothing below 14 px", () => {
    expect(token("text-base")).toBe("18px");
    expect(token("text-small")).toBe("14px");
    expect(token("text-h1")).toBe("32px");
    expect(Number.parseInt(token("text-small"), 10)).toBeGreaterThanOrEqual(14);
  });

  it("draws a 2 px focus ring with a 2 px offset", () => {
    expect(tokensCss).toContain("outline: 2px solid var(--focus);");
    expect(tokensCss).toContain("outline-offset: 2px;");
  });

  it("disables animation and transitions for reduced motion", () => {
    expect(tokensCss).toContain("prefers-reduced-motion: reduce");
    expect(tokensCss).toContain("animation: none !important;");
    expect(tokensCss).toContain("transition: none !important;");
  });
});
