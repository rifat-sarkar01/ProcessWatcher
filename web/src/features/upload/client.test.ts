import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api";

import { createUploadApi } from "./client";
import { PREVIEW } from "./test-fixtures";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("upload API client", () => {
  it("posts SOP text as JSON with the access code", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(PREVIEW));
    const api = createUploadApi({ accessCode: "s3cret", fetchImpl });

    const preview = await api.compile({ text: "1. Unplug.\n2. Remove." });

    expect(preview.step_graph.steps).toHaveLength(2);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/sop/compile");
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("X-Access-Code")).toBe("s3cret");
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ sop_text: "1. Unplug.\n2. Remove." }));
  });

  it("posts a SOP file as multipart", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(PREVIEW));
    const api = createUploadApi({ fetchImpl, baseUrl: "https://api.test/" });

    await api.compile({ file: new File(["1. A\n2. B\n"], "sop.md", { type: "text/markdown" }) });

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.test/sop/compile");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Headers).get("Content-Type")).toBeNull();
  });

  it("maps 401 and 413 to typed errors", async () => {
    const unauthorized = createUploadApi({
      fetchImpl: vi.fn(async () =>
        jsonResponse({ error: { code: "E-05", message: "Access code required." } }, 401),
      ),
    });
    const tooLarge = createUploadApi({ fetchImpl: vi.fn(async () => jsonResponse({}, 413)) });

    await expect(unauthorized.compile({ text: "x" })).rejects.toMatchObject({
      code: "unauthorized",
      status: 401,
    });
    await expect(tooLarge.compile({ text: "x" })).rejects.toBeInstanceOf(ApiError);
    await expect(tooLarge.compile({ text: "x" })).rejects.toMatchObject({ code: "too_large" });
  });

  it("starts a run with the video and SOP", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ run_id: "run_1", status: "queued" }, 202));
    const api = createUploadApi({ fetchImpl });

    const started = await api.startRun({
      video: new File(["v"], "clip.mp4", { type: "video/mp4" }),
      sopText: "1. A\n2. B\n",
      stepGraph: {
        schema_version: "1.0.0",
        sop_id: "sop_00000000",
        title: "Edited",
        source: { kind: "pasted", sha256: "a".repeat(64) },
        steps: [],
        vocabulary: { sam_concepts: ["hand"] },
        warnings: [],
      },
    });

    expect(started.run_id).toBe("run_1");
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    const form = init.body as FormData;
    expect(form.get("video")).toBeInstanceOf(File);
    expect(form.get("sop_text")).toBe("1. A\n2. B\n");
    const graph = JSON.parse(String(form.get("step_graph"))) as { title: string };
    expect(graph.title).toBe("Edited");
  });

  it("reports a network failure as ApiError", async () => {
    const api = createUploadApi({
      fetchImpl: vi.fn(async () => {
        throw new Error("offline");
      }),
    });

    await expect(api.compile({ text: "x" })).rejects.toMatchObject({ code: "network" });
  });
});
