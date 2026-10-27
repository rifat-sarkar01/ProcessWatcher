import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccessGate } from "./access-gate";

function typeCode(value: string) {
  fireEvent.change(screen.getByLabelText("Access code"), { target: { value } });
}

describe("AccessGate", () => {
  it("renders the gate with a labelled input and a submit button", () => {
    render(<AccessGate onSubmit={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Access code required" })).toBeInTheDocument();
    expect(screen.getByLabelText("Access code")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("submits the trimmed code", () => {
    const onSubmit = vi.fn();
    render(<AccessGate onSubmit={onSubmit} />);

    typeCode("  s3cret  ");
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(onSubmit).toHaveBeenCalledWith("s3cret");
  });

  it("rejects a code that is too short without calling onSubmit", () => {
    const onSubmit = vi.fn();
    render(<AccessGate onSubmit={onSubmit} />);

    typeCode("abc");
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("at least 4 characters");
    expect(screen.getByLabelText("Access code")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows a server-side rejection as an alert", () => {
    render(<AccessGate onSubmit={vi.fn()} error="That access code was not accepted." />);

    expect(screen.getByRole("alert")).toHaveTextContent("not accepted");
  });

  it("disables the button while checking", () => {
    render(<AccessGate onSubmit={vi.fn()} busy />);

    expect(screen.getByRole("button", { name: "Checking…" })).toBeDisabled();
  });
});
