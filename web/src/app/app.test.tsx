import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { AppRoutes } from "./router";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("app routes", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("renders the shell with the product heading and primary navigation", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { level: 1, name: "Process Watcher" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check a procedure" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Demo" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toBeInTheDocument();
  });

  it("shows the access gate on the landing route when no code is stored", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { name: "Access code required" })).toBeInTheDocument();
  });

  it("shows the empty run list when a code is already stored", () => {
    window.sessionStorage.setItem("pw.access-code", "s3cret");

    renderAt("/");

    expect(screen.getByRole("heading", { name: "No runs yet" })).toBeInTheDocument();
  });

  it("renders the run route with the run id", () => {
    renderAt("/runs/run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ");

    expect(screen.getByRole("heading", { name: /run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ/ })).toBeInTheDocument();
  });

  it("renders the demo route", () => {
    renderAt("/demo");

    expect(screen.getByRole("heading", { name: "Demo cases" })).toBeInTheDocument();
  });

  it("renders a not-found state for an unknown route", () => {
    renderAt("/nope");

    expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
  });
});
