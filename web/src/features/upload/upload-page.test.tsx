import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api";

import type { UploadApi } from "./client";
import { PREVIEW, STEPS } from "./test-fixtures";
import { UploadPage } from "./upload-page";

function fakeApi(overrides: Partial<UploadApi> = {}): UploadApi {
  return {
    compile: vi.fn(async () => PREVIEW),
    startRun: vi.fn(async () => ({ run_id: "run_01ABC", status: "queued" })),
    ...overrides,
  };
}

function videoFile(): File {
  return new File(["video"], "clip.mp4", { type: "video/mp4" });
}

async function compilePreview(api: UploadApi): Promise<UploadApi> {
  fireEvent.change(screen.getByLabelText("SOP text"), {
    target: { value: "1. Unplug.\n2. Remove." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Compile SOP" }));
  await waitFor(() => expect(screen.getByLabelText("Step 1 text")).toBeInTheDocument());
  return api;
}

describe("UploadPage", () => {
  it("labels the dropzones, SOP textarea and compile button", () => {
    render(<UploadPage api={fakeApi()} />);

    expect(screen.getByLabelText("Procedure video")).toHaveAttribute("type", "file");
    expect(screen.getByLabelText("Written SOP")).toHaveAttribute("type", "file");
    expect(screen.getByLabelText("SOP text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compile SOP" })).toBeInTheDocument();
  });

  it("compiles the pasted SOP and renders the editable steps", async () => {
    const api = fakeApi();
    render(<UploadPage api={api} />);

    await compilePreview(api);

    expect(api.compile).toHaveBeenCalledWith({ text: "1. Unplug.\n2. Remove." });
    expect(screen.getByRole("heading", { name: "Cable check" })).toBeInTheDocument();
    expect(screen.getByLabelText("Step 2 text")).toHaveValue("Remove the cover.");
    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled();
  });

  it("keeps Start disabled while the graph is invalid", async () => {
    const api = fakeApi();
    render(<UploadPage api={api} />);
    await compilePreview(api);
    fireEvent.change(screen.getByLabelText("Procedure video"), {
      target: { files: [videoFile()] },
    });

    fireEvent.change(screen.getByLabelText("Step 2 text"), { target: { value: "" } });

    expect(screen.getByRole("alert")).toHaveTextContent("Step 2 needs text.");
    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled();
  });

  it("starts the run once a video and a valid graph exist", async () => {
    const api = fakeApi();
    render(<UploadPage api={api} />);
    await compilePreview(api);
    fireEvent.change(screen.getByLabelText("Procedure video"), {
      target: { files: [videoFile()] },
    });

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(screen.getByText(/run_01ABC/)).toBeInTheDocument());
    expect(api.startRun).toHaveBeenCalledTimes(1);
    expect(api.startRun).toHaveBeenCalledWith(
      expect.objectContaining({
        stepGraph: expect.objectContaining({
          sop_id: "sop_01234567",
          steps: expect.arrayContaining([
            expect.objectContaining({ id: "stp_01", text: "Unplug the power cable." }),
          ]),
        }),
      }),
    );
  });

  it("preserves reordering in the rendered editor", async () => {
    const api = fakeApi();
    render(<UploadPage api={api} />);
    await compilePreview(api);

    fireEvent.click(screen.getByRole("button", { name: "Move step 1 down" }));

    expect(screen.getByLabelText("Step 1 text")).toHaveValue("Remove the cover.");
    expect(screen.getByLabelText("Step 2 text")).toHaveValue("Unplug the power cable.");
  });

  it("shows a typed API error as an alert", async () => {
    const api = fakeApi({
      compile: vi.fn(async () => {
        throw new ApiError("unauthorized", 401, "Access code required.");
      }),
    });
    render(<UploadPage api={api} />);

    fireEvent.change(screen.getByLabelText("SOP text"), { target: { value: "1. A\n2. B" } });
    fireEvent.click(screen.getByRole("button", { name: "Compile SOP" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Access code required."),
    );
  });

  it("rejects a non-video upload with a typed message", () => {
    render(<UploadPage api={fakeApi()} />);

    fireEvent.change(screen.getByLabelText("Procedure video"), {
      target: { files: [new File(["x"], "notes.pdf", { type: "application/pdf" })] },
    });

    expect(screen.getByRole("alert")).toHaveTextContent("That file type isn't supported.");
  });

  it("places step inputs after the compile controls in document order", () => {
    render(<UploadPage api={fakeApi()} initialSteps={STEPS} />);

    const compileButton = screen.getByRole("button", { name: "Compile SOP" });
    const first = screen.getByLabelText("Step 1 text");
    const second = screen.getByLabelText("Step 2 text");

    const firstAfter = compileButton.compareDocumentPosition(first);
    expect(firstAfter & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
