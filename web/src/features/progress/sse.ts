/**
 * Minimal SSE reader over a `ReadableStream`.
 *
 * The API guards `/runs/{id}/events` with `X-Access-Code`, which the platform
 * `EventSource` cannot send, so the progress view uses `fetch` and parses the
 * `text/event-stream` body itself. Only the subset the server emits is supported:
 * `event:`/`data:` lines, comment keep-alives, CRLF or LF, multi-line data.
 */

export interface SseFrame {
  event: string;
  data: string;
}

function parseBlock(block: string): SseFrame | null {
  let event = "message";
  const data: string[] = [];

  for (const rawLine of block.split(/\r?\n/)) {
    if (rawLine.length === 0 || rawLine.startsWith(":")) continue;
    const colon = rawLine.indexOf(":");
    const field = colon === -1 ? rawLine : rawLine.slice(0, colon);
    let value = colon === -1 ? "" : rawLine.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }

  return data.length === 0 ? null : { event, data: data.join("\n") };
}

export async function* readSseFrames(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseFrame> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.search(/\r?\n\r?\n/);
      while (boundary !== -1) {
        const match = buffer.slice(boundary).match(/^\r?\n\r?\n/);
        const separator = match ? match[0].length : 2;
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + separator);
        const frame = parseBlock(block);
        if (frame) yield frame;
        boundary = buffer.search(/\r?\n\r?\n/);
      }
    }
    buffer += decoder.decode();
    const tail = parseBlock(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}
