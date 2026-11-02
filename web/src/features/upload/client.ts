/**
 * Upload-flow HTTP calls: compile preview (`POST /sop/compile`) and run start
 * (`POST /runs`). Errors become the shared typed `ApiError`, so callers branch on code.
 */

import { ApiError, errorCodeForStatus } from "../../api";

import type { CompilePreview, StepGraph } from "./types";

export interface CompileInput {
  text?: string;
  file?: File;
}

export interface StartRunInput {
  video: File;
  sop?: File | null;
  sopText?: string | null;
  stepGraph?: StepGraph | null;
}

export interface StartedRun {
  run_id: string;
  status: string;
}

export interface UploadApi {
  compile(input: CompileInput): Promise<CompilePreview>;
  startRun(input: StartRunInput): Promise<StartedRun>;
}

export interface UploadApiOptions {
  baseUrl?: string;
  accessCode?: string | null;
  fetchImpl?: typeof fetch;
}

async function detailFrom(response: Response): Promise<string | null> {
  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object" && "error" in payload) {
      const error = (payload as { error?: unknown }).error;
      if (error && typeof error === "object" && "message" in error) {
        const message = (error as { message?: unknown }).message;
        if (typeof message === "string" && message.length > 0) return message;
      }
    }
  } catch {
    // Not JSON: keep the status-derived default message.
  }
  return null;
}

async function send(
  fetchImpl: typeof fetch,
  url: string,
  init: RequestInit,
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(url, init);
  } catch {
    throw new ApiError("network", 0);
  }
  if (!response.ok) {
    throw new ApiError(
      errorCodeForStatus(response.status),
      response.status,
      (await detailFrom(response)) ?? undefined,
    );
  }
  try {
    return (await response.json()) as unknown;
  } catch {
    throw new ApiError("invalid_response", response.status);
  }
}

export function createUploadApi(options: UploadApiOptions = {}): UploadApi {
  const baseUrl = (options.baseUrl ?? "").replace(/\/+$/, "");
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const accessCode = options.accessCode ?? null;

  function headers(extra?: Record<string, string>): Headers {
    const result = new Headers(extra);
    result.set("Accept", "application/json");
    if (accessCode) result.set("X-Access-Code", accessCode);
    return result;
  }

  return {
    async compile(input: CompileInput): Promise<CompilePreview> {
      let body: BodyInit;
      if (input.file) {
        const form = new FormData();
        form.append("sop", input.file);
        body = form;
      } else {
        body = JSON.stringify({ sop_text: input.text ?? "" });
      }
      const payload = await send(fetchImpl, `${baseUrl}/sop/compile`, {
        method: "POST",
        headers: headers(input.file ? undefined : { "Content-Type": "application/json" }),
        body,
      });
      return payload as CompilePreview;
    },

    async startRun(input: StartRunInput): Promise<StartedRun> {
      const form = new FormData();
      form.append("video", input.video, input.video.name);
      if (input.sop) form.append("sop", input.sop, input.sop.name);
      if (input.sopText && !input.sop) form.append("sop_text", input.sopText);
      if (input.stepGraph) form.append("step_graph", JSON.stringify(input.stepGraph));
      const payload = await send(fetchImpl, `${baseUrl}/runs`, {
        method: "POST",
        headers: headers(),
        body: form,
      });
      return payload as StartedRun;
    },
  };
}
