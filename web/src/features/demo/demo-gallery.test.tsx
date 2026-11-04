import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type ApiClient } from "../../api";
import type { DemoCaseSummary } from "../../api/demo";
import { DemoGallery } from "./demo-gallery";

const CASES: DemoCaseSummary[] = [
  {
    case_id: "keyboard-compliant",
    title: "Keyboard clean: compliant run",
    description: "The operator follows the SOP; no finding is flagged, only one review-level note.",
    source_run: "run_01M6GJTQVVQF26EWF0GYGZKZWD",
    duration_s: 54.3333,
    deviation_count: 1,
  },
  {
    case_id: "keyboard-heldout-missed-blower",
    title: "Held-out clip: blower step omitted",
    description: "A held-out recording with the blow-air step missing.",
    source_run: "run_01M6GK7GPYN345CN99WHECZ4CJ",
    duration_s: 28.2,
    deviation_count: 4,
  },
  {
    case_id: "keyboard-missed-tilt",
    title: "Keyboard clean: tilt and tap omitted",
    description: "Step 1 is never performed.",
    source_run: "run_01M6GERP2Y0GPDYV2AYJV77YAA",
    duration_s: 28.4667,
    deviation_count: 3,
  },
];

function fakeClient(cases: DemoCaseSummary[] = CASES): ApiClient {
  return {
    setAccessCode: vi.fn(),
    get: vi.fn(async () => ({ cases })) as unknown as ApiClient["get"],
  };
}

describe("DemoGallery", () => {
  it("lists the three frozen cases", async () => {
    render(<DemoGallery client={fakeClient()} onOpen={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Demo cases" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /Keyboard clean: compliant run/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /blower step omitted/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /tilt and tap omitted/i }),
    ).toBeInTheDocument();
  });

  it("labels every case as IT hardware", async () => {
    render(<DemoGallery client={fakeClient()} onOpen={vi.fn()} />);

    await screen.findByRole("button", { name: /Keyboard clean: compliant run/i });

    expect(screen.getAllByText("IT hardware")).toHaveLength(3);
  });

  it("carries a permanent offline badge", async () => {
    render(<DemoGallery client={fakeClient()} onOpen={vi.fn()} />);

    expect(screen.getByText("Offline")).toBeInTheDocument();
    expect(
      await screen.findByText(/no outbound network or model calls/i),
    ).toBeInTheDocument();
  });

  it("opens a case when it is clicked", async () => {
    const onOpen = vi.fn();
    render(<DemoGallery client={fakeClient()} onOpen={onOpen} />);

    fireEvent.click(await screen.findByRole("button", { name: /blower step omitted/i }));

    expect(onOpen).toHaveBeenCalledWith("keyboard-heldout-missed-blower");
  });

  it("states how many findings each case has", async () => {
    render(<DemoGallery client={fakeClient()} onOpen={vi.fn()} />);

    expect(
      await screen.findByRole("button", { name: /Keyboard clean: compliant run/i }),
    ).toHaveTextContent("1 finding");
    expect(screen.getByRole("button", { name: /blower step omitted/i })).toHaveTextContent(
      "4 findings",
    );
    expect(screen.getByRole("button", { name: /tilt and tap omitted/i })).toHaveTextContent(
      "3 findings",
    );
  });

  it("renders an empty state when there are no cases", async () => {
    render(<DemoGallery client={fakeClient([])} onOpen={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "No demo cases" })).toBeInTheDocument();
  });

  it("shows the API error instead of an empty gallery", async () => {
    const client: ApiClient = {
      setAccessCode: vi.fn(),
      get: vi.fn(async () => {
        throw new ApiError("network", 0);
      }) as unknown as ApiClient["get"],
    };

    render(<DemoGallery client={client} onOpen={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not reach the Process Watcher API.",
    );
  });
});
