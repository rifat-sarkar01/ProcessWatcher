import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Banner, EmptyState, LoadingState } from "./states";

describe("Banner", () => {
  it("announces info as a polite status", () => {
    render(<Banner tone="info">Analysis is running.</Banner>);

    expect(screen.getByRole("status")).toHaveTextContent("Analysis is running.");
  });

  it("announces errors assertively", () => {
    render(<Banner tone="error">The stage failed.</Banner>);

    expect(screen.getByRole("alert")).toHaveTextContent("The stage failed.");
  });

  it("renders an optional action", () => {
    render(
      <Banner tone="warning" action={<button type="button">Retry</button>}>
        Partial results
      </Banner>,
    );

    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("renders a title, help text and optional action", () => {
    render(
      <EmptyState
        title="No deviations found"
        help="Every step was observed in order."
        action={<a href="/demo">Open demo</a>}
      />,
    );

    expect(screen.getByRole("heading", { name: "No deviations found" })).toBeInTheDocument();
    expect(screen.getByText("Every step was observed in order.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open demo" })).toBeInTheDocument();
  });
});

describe("LoadingState", () => {
  it("is a polite live region with a label", () => {
    render(<LoadingState label="Loading the run…" />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Loading the run…");
    expect(status).toHaveAttribute("aria-live", "polite");
  });
});
