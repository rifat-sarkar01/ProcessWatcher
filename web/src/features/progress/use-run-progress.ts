import { useCallback, useEffect, useState } from "react";

import { initialProgress, parseEvent, reduceProgress, type ProgressState } from "./events";
import { readSseFrames } from "./sse";

/** The slice of `fetch` the progress stream needs, so tests can inject a stream. */
export interface StreamResponse {
  ok: boolean;
  status: number;
  body: ReadableStream<Uint8Array> | null;
}

export type StreamFetch = (
  url: string,
  init: { headers: Record<string, string>; signal: AbortSignal },
) => Promise<StreamResponse>;

export interface UseRunProgressOptions {
  runId: string;
  accessCode?: string | null;
  baseUrl?: string;
  fetchImpl?: StreamFetch;
  maxRetries?: number;
  retryDelayMs?: number;
  /** Skip the network entirely; used by tests and by the frozen demo mode. */
  initial?: ProgressState;
}

export interface RunProgressController {
  state: ProgressState;
  error: string | null;
  retry: () => void;
}

const defaultFetch: StreamFetch = async (url, init) => globalThis.fetch(url, init);

function messageForStatus(status: number): string {
  if (status === 401 || status === 403) return "Session expired. Enter the access code again.";
  if (status === 404) return "Run not found or expired.";
  if (status === 429) return "Too many requests. Try again in a moment.";
  return "Could not open the progress stream. Try again.";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function useRunProgress({
  runId,
  accessCode = null,
  baseUrl = "",
  fetchImpl,
  maxRetries = 2,
  retryDelayMs = 500,
  initial,
}: UseRunProgressOptions): RunProgressController {
  const [state, setState] = useState<ProgressState>(() => initial ?? initialProgress());
  const [error, setError] = useState<string | null>(null);
  const [attemptKey, setAttemptKey] = useState(0);

  const retry = useCallback(() => {
    setError(null);
    setState((current) => ({ ...current, connection: "connecting" }));
    setAttemptKey((key) => key + 1);
  }, []);

  useEffect(() => {
    if (initial) return;
    const controller = new AbortController();
    let cancelled = false;

    const headers: Record<string, string> = { Accept: "text/event-stream" };
    if (accessCode) headers["X-Access-Code"] = accessCode;
    const url = `${baseUrl.replace(/\/+$/, "")}/runs/${encodeURIComponent(runId)}/events`;
    const streamFetch = fetchImpl ?? defaultFetch;

    const stream = async () => {
      for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
        if (cancelled) return;

        let response: StreamResponse;
        try {
          response = await streamFetch(url, { headers, signal: controller.signal });
        } catch {
          if (cancelled) return;
          if (attempt < maxRetries) {
            setState((current) => ({ ...current, connection: "retrying" }));
            await delay(retryDelayMs);
            continue;
          }
          setState((current) => ({ ...current, connection: "closed" }));
          setError("Connection lost. Try again.");
          return;
        }

        if (!response.ok) {
          setState((current) => ({ ...current, connection: "closed" }));
          setError(messageForStatus(response.status));
          return;
        }

        setState((current) => ({ ...current, connection: "open" }));
        if (!response.body) {
          setState((current) => ({ ...current, connection: "closed" }));
          return;
        }

        try {
          for await (const frame of readSseFrames(response.body)) {
            if (cancelled) return;
            const event = parseEvent(frame.event, frame.data);
            setState((current) => reduceProgress(current, event));
            if (event.kind === "done") {
              setState((current) => ({ ...current, connection: "closed" }));
              return;
            }
          }
        } catch {
          // Aborted or the socket died mid-frame: fall through to the retry path.
        }

        if (cancelled) return;
        if (attempt < maxRetries) {
          setState((current) => ({ ...current, connection: "retrying" }));
          await delay(retryDelayMs);
          continue;
        }
        setState((current) => ({ ...current, connection: "closed" }));
        return;
      }
    };

    void stream();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [runId, accessCode, baseUrl, fetchImpl, maxRetries, retryDelayMs, initial, attemptKey]);

  return { state, error, retry };
}
