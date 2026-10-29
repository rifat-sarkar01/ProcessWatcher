import { describe, expect, it } from "vitest";

import { readSseFrames } from "./sse";

function streamOf(chunks: string[], chunkSize = 7): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(chunks.join(""));
  let offset = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      controller.enqueue(bytes.slice(offset, offset + chunkSize));
      offset += chunkSize;
    },
  });
}

async function collect(chunks: string[], chunkSize?: number) {
  const frames = [];
  for await (const frame of readSseFrames(streamOf(chunks, chunkSize))) {
    frames.push(frame);
  }
  return frames;
}

describe("readSseFrames", () => {
  it("parses a complete frame", async () => {
    const frames = await collect(['event: stage\ndata: {"stage": "ingest"}\n\n']);

    expect(frames).toEqual([{ event: "stage", data: '{"stage": "ingest"}' }]);
  });

  it("reassembles frames split at arbitrary byte boundaries", async () => {
    const frames = await collect(
      ['event: stage\ndata: {"pct": 100}\n\nevent: done\ndata: {"status": "done"}\n\n'],
      5,
    );

    expect(frames).toHaveLength(2);
    expect(frames[1]).toEqual({ event: "done", data: '{"status": "done"}' });
  });

  it("accepts CRLF line endings", async () => {
    const frames = await collect(["event: heartbeat\r\ndata: {\"elapsed_s\": 15}\r\n\r\n"]);

    expect(frames).toEqual([{ event: "heartbeat", data: '{"elapsed_s": 15}' }]);
  });

  it("skips comment lines used as keep-alives", async () => {
    const frames = await collect([": ping\n\nevent: done\ndata: {}\n\n"]);

    expect(frames).toEqual([{ event: "done", data: "{}" }]);
  });

  it("joins multi-line data with newlines", async () => {
    const frames = await collect(["event: stage\ndata: one\ndata: two\n\n"]);

    expect(frames[0]?.data).toBe("one\ntwo");
  });

  it("flushes a final frame that has no trailing blank line", async () => {
    const frames = await collect(["event: done\ndata: {}"]);

    expect(frames).toEqual([{ event: "done", data: "{}" }]);
  });
});
