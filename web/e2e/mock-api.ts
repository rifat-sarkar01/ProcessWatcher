import type { Page, Route } from "@playwright/test";

import { PNG_1X1, TINY_MP4 } from "./fixtures/media";
import { COMPILE_RESPONSE, REPORT, STAGE_EVENTS } from "./fixtures/replay";

export const RUN_ID = REPORT.run_id;
export const ACCESS_CODE = "demo-code";

const DEMO_CASES = [
  {
    case_id: "keyboard-compliant",
    title: "Keyboard clean: compliant run",
    description: "The operator follows the SOP; no finding is flagged, only one review-level note.",
    source_run: RUN_ID,
    duration_s: REPORT.video.duration_s,
    deviation_count: REPORT.deviations.length,
  },
  {
    case_id: "keyboard-heldout-missed-blower",
    title: "Held-out clip: blower step omitted",
    description: "A held-out recording with the blow-air step missing.",
    source_run: RUN_ID,
    duration_s: 28.2,
    deviation_count: 4,
  },
  {
    case_id: "keyboard-missed-tilt",
    title: "Keyboard clean: tilt and tap omitted",
    description: "Step 1 is never performed.",
    source_run: RUN_ID,
    duration_s: 28.4667,
    deviation_count: 3,
  },
];

export interface ReviewPatch {
  deviation_id: string;
  decision: string;
}

export interface MockApi {
  /** Decisions the UI sent to `PATCH /runs/{id}/review`. */
  reviewPatches: ReviewPatch[];
  /** How many `POST /runs` calls the UI made (multipart uploads). */
  startedRuns: number;
  /** Let `GET /runs/{id}` report `done` so the review screen loads. */
  finishRun(): void;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/**
 * Deterministic replay API: every request the UI makes is answered from fixtures
 * (`web/e2e/fixtures`), so the journey never touches a model or the network.
 *
 * The run stays `running` until the test calls `finishRun()`, which keeps the progress
 * assertion independent of timing; the SSE stream replays all 12 stages immediately.
 */
export async function installMockApi(page: Page): Promise<MockApi> {
  let finished = false;
  const reviewPatches: ReviewPatch[] = [];
  const state: MockApi = {
    reviewPatches,
    startedRuns: 0,
    finishRun() {
      finished = true;
    },
  };

  await page.context().route("**/*", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/sop/compile" && method === "POST") {
      await json(route, COMPILE_RESPONSE);
      return;
    }

    if (path === "/runs" && method === "POST") {
      state.startedRuns += 1;
      await json(route, { run_id: RUN_ID, status: "running" });
      return;
    }

    if (path === `/runs/${RUN_ID}` && method === "GET") {
      await json(route, { run_id: RUN_ID, status: finished ? "done" : "running" });
      return;
    }

    if (path === `/runs/${RUN_ID}/events`) {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "Cache-Control": "no-cache" },
        body: STAGE_EVENTS,
      });
      return;
    }

    if (path === `/runs/${RUN_ID}/report` && method === "GET") {
      await json(route, REPORT);
      return;
    }

    if (path === `/runs/${RUN_ID}/review` && method === "PATCH") {
      reviewPatches.push(JSON.parse(request.postData() ?? "{}") as ReviewPatch);
      await json(route, { schema_version: "1.0.0", decisions: [] });
      return;
    }

    if (path.startsWith(`/runs/${RUN_ID}/artifacts/`)) {
      const artifact = path.slice(`/runs/${RUN_ID}/artifacts/`.length);
      if (artifact === "report.html") {
        await route.fulfill({
          status: 200,
          contentType: "text/html",
          body: `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Process Watcher report</title></head><body><h1>Report ${RUN_ID}</h1><p>Self-contained audit report.</p></body></html>`,
        });
        return;
      }
      if (artifact.endsWith(".png")) {
        await route.fulfill({ status: 200, contentType: "image/png", body: PNG_1X1 });
        return;
      }
      if (artifact.endsWith(".mp4")) {
        await route.fulfill({ status: 200, contentType: "video/mp4", body: TINY_MP4 });
        return;
      }
    }

    if (path === "/demo/cases" && method === "GET") {
      await json(route, { cases: DEMO_CASES });
      return;
    }

    if (path.startsWith("/demo/cases/") && method === "GET" && !path.endsWith(".mp4")) {
      const caseId = path.slice("/demo/cases/".length);
      const summary = DEMO_CASES.find((item) => item.case_id === caseId);
      if (summary) {
        await json(route, {
          ...summary,
          media: { analysis: "media/analysis.mp4" },
          report: REPORT,
        });
        return;
      }
    }

    if (path.startsWith("/demo/cases/") && path.endsWith(".mp4")) {
      await route.fulfill({ status: 200, contentType: "video/mp4", body: TINY_MP4 });
      return;
    }

    await route.fallback();
  });

  return state;
}
