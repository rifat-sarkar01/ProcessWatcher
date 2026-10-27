import axe from "axe-core";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "../app/router";

/**
 * axe over the four shipped routes (T-6.7).
 *
 * `color-contrast` is disabled here because jsdom has no layout engine and therefore
 * no computed colours; contrast is asserted against the design tokens themselves in
 * `tokens.test.ts`, which is stricter than a DOM guess.
 */
const ROUTES = [
  "/",
  "/runs/run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ",
  "/demo",
  "/demo/ssd-swap",
] as const;

async function audit(path: string) {
  window.sessionStorage.clear();
  const { container } = render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );

  const results = await axe.run(container, {
    rules: {
      "color-contrast": { enabled: false },
    },
  });

  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

describe("accessibility", () => {
  beforeEach(() => {
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    // jsdom has no canvas; axe probes it and would log a "Not implemented" warning.
    vi.spyOn(window.HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each(ROUTES)("route %s has no serious or critical axe violations", async (path) => {
    const violations = await audit(path);

    expect(violations.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
  });

  it("detects a planted violation, proving the harness is real", async () => {
    const { container } = render(<img src="planted.png" />);

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });

    expect(results.violations.map((violation) => violation.id)).toContain("image-alt");
  });
});
