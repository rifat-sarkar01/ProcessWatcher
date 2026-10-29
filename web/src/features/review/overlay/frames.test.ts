import { describe, expect, it } from "vitest";

import type { Track } from "../../../types/generated/tracks";

import { OVERLAY_PALETTE, frameAt, holdsOf, trackColour } from "./frames";

function track(id: string, concept: string, samples: Array<[number, number[]]>): Track {
  return {
    id,
    concept,
    first_t: samples[0]?.[0] ?? 0,
    last_t: samples.at(-1)?.[0] ?? 0,
    frames: samples.map(([t, box], index) => ({ frame: index, t, box, score: 0.9 })),
  };
}

const ONE_TRACK = [
  track("trk_001", "screwdriver", [
    [0.0, [0.1, 0.1, 0.3, 0.3]],
    [0.1, [0.11, 0.1, 0.31, 0.3]],
    [0.2, [0.12, 0.1, 0.32, 0.3]],
    [2.0, [0.5, 0.5, 0.7, 0.7]],
  ]),
  track("trk_002", "bolt", [[1.0, [0.5, 0.6, 0.6, 0.7]]]),
];

describe("frameAt", () => {
  it("picks the sample at the queried time", () => {
    const [first, second] = frameAt(ONE_TRACK, 0.1, 15);

    expect(first?.trackId).toBe("trk_001");
    expect(first?.box).toEqual([0.11, 0.1, 0.31, 0.3]);
    expect(second).toBeUndefined();
  });

  it("keeps the nearest sample inside one frame interval", () => {
    const [item] = frameAt(ONE_TRACK, 0.13, 15);

    expect(item?.trackId).toBe("trk_001");
    expect(item?.box[0]).toBeCloseTo(0.11);
  });

  it("draws nothing when the gap to the next sample is too large", () => {
    expect(frameAt(ONE_TRACK, 1.2, 15)).toEqual([]);
    expect(frameAt(ONE_TRACK, 5, 15)).toEqual([]);
  });

  it("returns one item per visible track, sorted by id", () => {
    const items = frameAt(ONE_TRACK, 2.0, 15);

    expect(items.map((item) => item.trackId)).toEqual(["trk_001"]);
    const both = frameAt(
      [track("trk_002", "bolt", [[1.0, [0, 0, 1, 1]]]), track("trk_001", "hand", [[1.0, [0, 0, 1, 1]]])],
      1.0,
      15,
    );
    expect(both.map((item) => item.trackId)).toEqual(["trk_001", "trk_002"]);
  });

  it("carries the polygon when the sample has one", () => {
    const withPoly: Track = {
      ...track("trk_003", "hand", [[1.0, [0.2, 0.2, 0.4, 0.4]]]),
      frames: [
        {
          frame: 0,
          t: 1.0,
          box: [0.2, 0.2, 0.4, 0.4],
          score: 0.8,
          poly: [
            [0.2, 0.2],
            [0.4, 0.25],
            [0.35, 0.4],
          ],
        },
      ],
    };

    const [item] = frameAt([withPoly], 1.0, 15);

    expect(item?.poly).toHaveLength(3);
    expect(item?.score).toBeCloseTo(0.8);
  });

  it("handles an empty track list", () => {
    expect(frameAt([], 3, 15)).toEqual([]);
  });
});

describe("holdsOf", () => {
  it("groups consecutive samples into holds and splits on gaps", () => {
    const holds = holdsOf(ONE_TRACK[0] as Track);

    expect(holds).toHaveLength(2);
    expect(holds[0]).toMatchObject({ tStart: 0, tEnd: 0.2, samples: 3 });
    expect(holds[1]).toMatchObject({ tStart: 2, tEnd: 2, samples: 1 });
  });

  it("reports the mean score per hold", () => {
    const holds = holdsOf({
      ...track("trk_004", "hand", [
        [0, [0, 0, 1, 1]],
        [0.1, [0, 0, 1, 1]],
      ]),
    });

    expect(holds[0]?.meanScore).toBeCloseTo(0.9);
  });

  it("returns nothing for a track without frames", () => {
    expect(holdsOf({ id: "trk_005", concept: "hand", first_t: 0, last_t: 0, frames: [] })).toEqual(
      [],
    );
  });
});

describe("trackColour", () => {
  it("is deterministic per track id and drawn from the spec palette", () => {
    expect(trackColour("trk_007")).toBe(trackColour("trk_007"));
    expect(OVERLAY_PALETTE).toContain(trackColour("trk_007"));
  });

  it("spreads ids across the palette", () => {
    const colours = new Set(
      Array.from({ length: 10 }, (_, index) => trackColour(`trk_00${index}`)),
    );

    expect(colours.size).toBeGreaterThan(3);
  });
});
