import { Buffer } from "node:buffer";

import { expect, test, type Locator } from "@playwright/test";

import { TINY_MP4 } from "./fixtures/media";
import { COMPILE_RESPONSE } from "./fixtures/replay";
import { ACCESS_CODE, RUN_ID, installMockApi } from "./mock-api";

const SOP_TEXT = [
  "# Cable check",
  "",
  "1. Power the unit down.",
  "2. Unplug the power cable.",
  "3. Remove the cover.",
].join("\n");

async function imageLoaded(image: Locator): Promise<boolean> {
  return image.evaluate(
    (element: HTMLImageElement) => element.complete && element.naturalWidth > 0,
  );
}

test("replay journey: access, upload, edit, progress, review, accept, export", async ({
  page,
}) => {
  const api = await installMockApi(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Access code required" })).toBeVisible();
  await page.getByLabel("Access code", { exact: true }).fill(ACCESS_CODE);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Check a procedure" })).toBeVisible();

  await page.getByLabel("Procedure video").setInputFiles({
    name: "demo.mp4",
    mimeType: "video/mp4",
    buffer: TINY_MP4,
  });
  await page.getByLabel("Written SOP").setInputFiles({
    name: "sop.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(SOP_TEXT, "utf-8"),
  });
  await expect(page.getByLabel("SOP text")).toHaveValue(/Power the unit down/);

  await page.getByRole("button", { name: "Compile SOP" }).click();
  await expect(
    page.getByRole("heading", { name: COMPILE_RESPONSE.step_graph.title }),
  ).toBeVisible();
  await expect(page.getByLabel("Step 1 text")).toHaveValue("Power the unit down.");

  await page.getByLabel("Step 3 text").fill("Remove the rear cover.");
  await page.getByRole("button", { name: "Move step 3 up" }).click();
  await expect(page.getByLabel("Step 2 text")).toHaveValue("Remove the rear cover.");
  await expect(page.getByLabel("Step 3 text")).toHaveValue("Unplug the power cable.");

  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${RUN_ID}$`));
  await expect(page.getByRole("heading", { name: `Run ${RUN_ID}` })).toBeVisible();

  await expect(page.getByRole("list", { name: "Pipeline stages" })).toBeVisible();
  await expect(page.getByText("Run complete.", { exact: true })).toBeVisible();
  await expect(page.getByText("Report", { exact: true })).toBeVisible();

  api.finishRun();
  await expect(page.getByRole("heading", { name: "Deviations" })).toBeVisible();
  const card = page.getByTestId("deviation-dev_001");
  await expect(card).toBeVisible();
  await expect(card.getByText("Step 2 was not observed between step 1 and step 3.")).toBeVisible();

  const evidence = card.getByAltText(/^Evidence frame at/);
  await expect(evidence).toBeVisible();
  await expect.poll(() => imageLoaded(evidence)).toBe(true);
  await expect(card.getByText(/^EVIDENCE · real frame/)).toBeVisible();

  const illustration = card.getByAltText(/^AI illustration, not evidence:/);
  await expect(illustration).toBeVisible();
  await expect.poll(() => imageLoaded(illustration)).toBe(true);
  await expect(card.getByText("AI ILLUSTRATION · NOT EVIDENCE")).toBeVisible();
  await expect(card.getByText("What correct looks like (AI illustration, not evidence)")).toBeVisible();

  await page.getByRole("button", { name: "Accept dev_001" }).click();
  await expect(page.getByTestId("decision-dev_001")).toHaveText("Accepted");
  await expect.poll(() => api.reviewPatches.length).toBe(1);
  expect(api.reviewPatches[0]).toMatchObject({
    deviation_id: "dev_001",
    decision: "accepted",
  });
  expect(api.startedRuns).toBe(1);

  const popupPromise = page.context().waitForEvent("page");
  await page.getByRole("button", { name: "Export report" }).click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(new RegExp(`/runs/${RUN_ID}/artifacts/report\\.html$`));
  await expect(popup.getByRole("heading", { name: `Report ${RUN_ID}` })).toBeVisible();
});

test("demo gallery: three offline cases open the frozen review", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/demo");

  await expect(page.getByRole("heading", { name: "Demo cases" })).toBeVisible();
  await expect(page.getByText("Offline", { exact: true })).toBeVisible();
  const cards = page.getByRole("button", { name: /finding/ });
  await expect(cards).toHaveCount(3);

  await page
    .getByRole("button", { name: /SSD swap: skipped power reconnect/ })
    .click();
  await expect(page).toHaveURL(/\/demo\/ssd-swap$/);
  await expect(
    page.getByRole("heading", { name: "SSD swap: skipped power reconnect" }),
  ).toBeVisible();
  await expect(page.getByText("Offline", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "All demo cases" }).click();
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("heading", { name: "Demo cases" })).toBeVisible();
});
