import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DEMO_CASES } from "./cases";
import { DemoGallery } from "./demo-gallery";

describe("DemoGallery", () => {
  it("lists the three frozen cases", () => {
    render(<DemoGallery onOpen={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Demo cases" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /SSD swap/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /standard solution/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cross-pattern torque/i })).toBeInTheDocument();
  });

  it("shows the domain of every case", () => {
    render(<DemoGallery onOpen={vi.fn()} />);

    for (const demoCase of DEMO_CASES) {
      expect(screen.getByText(demoCase.domain)).toBeInTheDocument();
    }
  });

  it("carries a permanent offline badge", () => {
    render(<DemoGallery onOpen={vi.fn()} />);

    expect(screen.getByText("Offline")).toBeInTheDocument();
    expect(screen.getByText(/no network or model calls/i)).toBeInTheDocument();
  });

  it("opens a case when it is clicked", () => {
    const onOpen = vi.fn();
    render(<DemoGallery onOpen={onOpen} />);

    fireEvent.click(screen.getByRole("button", { name: /wrong tool/i }));

    expect(onOpen).toHaveBeenCalledWith("standard-solution");
  });

  it("states how many findings each case has", () => {
    render(<DemoGallery onOpen={vi.fn()} />);

    expect(screen.getByRole("button", { name: /SSD swap/i })).toHaveTextContent("1 finding");
    expect(screen.getByRole("button", { name: /cross-pattern torque/i })).toHaveTextContent(
      "2 findings",
    );
  });

  it("renders an empty state when there are no cases", () => {
    render(<DemoGallery cases={[]} onOpen={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "No demo cases" })).toBeInTheDocument();
  });
});
