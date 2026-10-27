import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DemoCasePage } from "./demo-case-page";

function renderCase(caseId: string) {
  return render(
    <MemoryRouter initialEntries={[`/demo/${caseId}`]}>
      <Routes>
        <Route path="demo/:caseId" element={<DemoCasePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DemoCasePage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });

  it("opens the review surface for the selected case", () => {
    renderCase("ssd-swap");

    expect(screen.getByRole("heading", { name: /SSD swap/ })).toBeInTheDocument();
    expect(screen.getByTestId("timeline")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("keeps the offline badge and links back to the gallery", () => {
    renderCase("ssd-swap");

    expect(screen.getByText("Offline")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All demo cases" })).toHaveAttribute(
      "href",
      "/demo",
    );
  });

  it("lists the case deviations in the timeline", () => {
    renderCase("cross-pattern-torque");

    expect(screen.getAllByTestId("deviation-marker")).toHaveLength(2);
  });

  it("shows a not-found state for an unknown case", () => {
    renderCase("does-not-exist");

    expect(screen.getByRole("heading", { name: "Case not found" })).toBeInTheDocument();
  });
});
