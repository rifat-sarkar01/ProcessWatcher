import { describe, expect, it } from "vitest";

import { simplifyPolygon } from "./simplify";

describe("simplifyPolygon", () => {
  it("keeps a triangle intact", () => {
    const points: Array<[number, number]> = [
      [0, 0],
      [10, 0],
      [5, 10],
    ];

    expect(simplifyPolygon(points, 1.5)).toHaveLength(3);
  });

  it("drops points that lie within the tolerance of the line", () => {
    const points: Array<[number, number]> = [
      [0, 0],
      [5, 0.5],
      [10, 0],
      [10, 10],
    ];

    const simplified = simplifyPolygon(points, 1.5);

    expect(simplified).toHaveLength(3);
    expect(simplified).not.toContainEqual([5, 0.5]);
  });

  it("keeps points beyond the tolerance", () => {
    const points: Array<[number, number]> = [
      [0, 0],
      [5, 4],
      [10, 0],
    ];

    expect(simplifyPolygon(points, 1.5)).toHaveLength(3);
  });

  it("never returns fewer than three points", () => {
    const points: Array<[number, number]> = [
      [0, 0],
      [1, 0.01],
      [2, 0],
      [3, 0.01],
    ];

    expect(simplifyPolygon(points, 100).length).toBeGreaterThanOrEqual(3);
  });

  it("passes degenerate inputs through", () => {
    expect(simplifyPolygon([], 1.5)).toEqual([]);
    expect(simplifyPolygon([[1, 2]], 1.5)).toEqual([[1, 2]]);
    expect(
      simplifyPolygon(
        [
          [1, 2],
          [3, 4],
        ],
        1.5,
      ),
    ).toHaveLength(2);
  });
});
