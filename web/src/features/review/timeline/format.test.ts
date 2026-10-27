import { describe, expect, it } from "vitest";

import { formatTimecode } from "./format";

describe("formatTimecode", () => {
  it("formats mm:ss.s", () => {
    expect(formatTimecode(0)).toBe("00:00.0");
    expect(formatTimecode(72.4)).toBe("01:12.4");
    expect(formatTimecode(65)).toBe("01:05.0");
  });

  it("rounds to one decimal", () => {
    expect(formatTimecode(9.96)).toBe("00:10.0");
  });

  it("handles clips longer than ten minutes", () => {
    expect(formatTimecode(605.5)).toBe("10:05.5");
  });

  it("clamps negative input to zero", () => {
    expect(formatTimecode(-2)).toBe("00:00.0");
  });
});
