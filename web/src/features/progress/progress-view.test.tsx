import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RunProgress } from "./progress-view";
import { initialProgress, parseEvent, reduceProgress, type ProgressState } from "./events";
import type { StreamFetch } from "./use-run-progress";

function stateAfter(...events: Array<[string, string]>): ProgressState {
  return events
    .map(([name, data]) => parseEvent(name, data))
    .reduce(reduceProgress, initialProgress());
}

function stage(name: string, status: string, extra: Record<string, unknown> = {}) {
  return JSON.stringify({ stage: name, status, pct: 100, elapsed_s: 3, cost_usd: 0, ...extra });
}

function streamOf(text: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

function fetchReturning(...chunks: string[]): StreamFetch {
  let call = 0;
  return vi.fn(async () => {
    const chunk = chunks[Math.min(call, chunks.length - 1)];
    call += 1;
    return { ok: true, status: 200, body: streamOf(chunk ?? "") };
  });
}

const ALL_DONE = [
  "ingest",
  "sop_compile",
  "perceive",
  "timeline",
  "identify",
  "score",
  "align",
  "deviations",
  "verify",
  "evidence",
  "illustrate",
  "report",
]
  .map((name) => `event: stage\ndata: ${stage(name, "done")}\n\n`)
  .join("");

describe("RunProgress stepper", () => {
  it("renders the 12 stages in pipeline order", () => {
    render(<RunProgress runId="run_1" initial={initialProgress()} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(12);
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining("Ingest"),
      expect.stringContaining("Compile SOP"),
      expect.stringContaining("Perceive"),
      expect.stringContaining("Timeline"),
      expect.stringContaining("Identify tools"),
      expect.stringContaining("Score segments"),
      expect.stringContaining("Align"),
      expect.stringContaining("Deviations"),
      expect.stringContaining("Verify"),
      expect.stringContaining("Evidence"),
      expect.stringContaining("Illustrate"),
      expect.stringContaining("Report"),
    ]);
  });

  it("marks the running stage as the current step with its percentage", () => {
    render(
      <RunProgress
        runId="run_1"
        initial={stateAfter(["stage", stage("perceive", "running", { pct: 42, elapsed_s: 6 })])}
      />,
    );

    const current = screen.getByRole("listitem", { current: "step" });
    expect(current).toHaveTextContent("Perceive");
    expect(current).toHaveTextContent("42%");
  });

  it("ticks finished stages and shows the run cost and elapsed time", () => {
    render(
      <RunProgress
        runId="run_1"
        initial={stateAfter(
          ["stage", stage("ingest", "done", { elapsed_s: 4 })],
          ["stage", stage("sop_compile", "done", { cost_usd: 0.12, elapsed_s: 9 })],
        )}
      />,
    );

    expect(screen.getAllByText("Done").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("$0.12 / $3.00")).toBeInTheDocument();
    expect(screen.getByText("00:09.0")).toBeInTheDocument();
  });

  it("turns the cost meter amber at 80% and red at the cap", () => {
    const { unmount } = render(
      <RunProgress
        runId="run_1"
        initial={stateAfter(["stage", stage("perceive", "done", { cost_usd: 2.4 })])}
      />,
    );
    expect(screen.getByTestId("cost-meter")).toHaveClass("text-dev-missed");
    unmount();

    render(
      <RunProgress
        runId="run_1"
        initial={stateAfter(["stage", stage("report", "done", { cost_usd: 3 })])}
      />,
    );
    expect(screen.getByTestId("cost-meter")).toHaveClass("text-error");
    expect(screen.getByRole("alert")).toHaveTextContent("Spend cap reached.");
  });

  it("offers the findings preview once align has finished", () => {
    render(
      <RunProgress
        runId="run_1"
        runHref="/runs/run_1"
        initial={stateAfter(
          ["stage", stage("align", "done")],
          ["stage", stage("verify", "running")],
        )}
      />,
    );

    expect(screen.getByRole("link", { name: "Preview findings" })).toHaveAttribute(
      "href",
      "/runs/run_1",
    );
  });

  it("banners a failed stage with its reason and a partial-report action", () => {
    const onContinue = vi.fn();
    render(
      <RunProgress
        runId="run_1"
        onContinue={onContinue}
        initial={stateAfter([
          "stage",
          stage("verify", "failed", { reason: "verifier timed out" }),
        ])}
      />,
    );

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("Stage Verify failed.");
    expect(banner).toHaveTextContent("verifier timed out");

    fireEvent.click(screen.getByRole("button", { name: "Continue with partial" }));
    expect(onContinue).toHaveBeenCalledWith("run_1");
  });

  it("announces completion politely", () => {
    render(
      <RunProgress
        runId="run_1"
        initial={stateAfter(["done", '{"status": "done"}'])}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Run complete.");
  });
});

describe("RunProgress stream", () => {
  it("consumes ordered SSE events and finishes at done", async () => {
    const fetchImpl = fetchReturning(
      `event: stage\ndata: ${stage("ingest", "done")}\n\n` +
        `event: stage\ndata: ${stage("sop_compile", "running", { pct: 50 })}\n\n`,
      `${ALL_DONE}event: done\ndata: {"status": "done"}\n\n`,
    );

    render(<RunProgress runId="run_1" accessCode="secret" fetchImpl={fetchImpl} />);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Run complete."));
    expect(screen.getAllByText("Done")).toHaveLength(12);
    const [, init] = vi.mocked(fetchImpl).mock.calls[0] ?? [];
    expect(init?.headers?.["X-Access-Code"]).toBe("secret");
  });

  it("reconnects and replays without duplicating stages", async () => {
    const fetchImpl = vi.fn<StreamFetch>();
    fetchImpl.mockRejectedValueOnce(new Error("connection reset"));
    fetchImpl.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: streamOf(`event: stage\ndata: ${stage("ingest", "done")}\n\nevent: done\ndata: {}\n\n`),
    });

    render(
      <RunProgress runId="run_1" fetchImpl={fetchImpl} retryDelayMs={0} />,
    );

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Run complete."));
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(screen.getAllByText("Done")).toHaveLength(1);
  });

  it("shows the failure banner when a stage fails mid-stream", async () => {
    render(
      <RunProgress
        runId="run_1"
        fetchImpl={fetchReturning(
          `event: stage\ndata: ${stage("verify", "failed", { reason: "retries exhausted" })}\n\n`,
        )}
      />,
    );

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("retries exhausted"),
    );
  });

  it("reports an expired session instead of hanging", async () => {
    const fetchImpl: StreamFetch = vi.fn(async () => ({ ok: false, status: 401, body: null }));

    render(<RunProgress runId="run_1" fetchImpl={fetchImpl} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Session expired. Enter the access code again."),
    );
  });
});
