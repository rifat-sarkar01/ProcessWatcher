import { useState } from "react";

import type { StepDraft } from "./types";
import { addTool, moveStep, removeTool, updateStep, validateSteps } from "./types";

export interface StepEditorProps {
  steps: StepDraft[];
  onChange: (steps: StepDraft[]) => void;
  disabled?: boolean;
}

const FIELD_CLASS =
  "w-full rounded-control border border-border-strong bg-bg px-3 py-2 text-control text-fg";

function ToolAdder({
  step,
  index,
  disabled,
  onAdd,
}: {
  step: StepDraft;
  index: number;
  disabled: boolean;
  onAdd: (tool: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const label = `New tool for step ${index + 1}`;

  function commit() {
    if (draft.trim()) {
      onAdd(draft);
      setDraft("");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <input
        aria-label={label}
        value={draft}
        disabled={disabled}
        placeholder="Add a tool"
        className={`${FIELD_CLASS} max-w-56`}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
          }
        }}
      />
      <button
        type="button"
        aria-label={`Add tool to step ${index + 1}`}
        disabled={disabled || !draft.trim()}
        onClick={commit}
        className="min-h-11 rounded-control border border-border-strong px-3 text-control disabled:opacity-50"
      >
        Add
      </button>
      {step.tools.length === 0 ? (
        <span className="text-small text-muted">No tools listed</span>
      ) : null}
    </div>
  );
}

/**
 * Editable step list: text, tools, critical flag, ordering and order. Step ids stay
 * stable; `idx` follows the visual order. Invalid graphs are shown but never blocked
 * from being fixed — the Start button is what validation gates.
 */
export function StepEditor({ steps, onChange, disabled = false }: StepEditorProps) {
  const issues = validateSteps(steps);

  return (
    <section aria-labelledby="steps-heading" className="flex flex-col gap-4">
      <div>
        <h2 id="steps-heading" className="m-0 text-h3 font-semibold">
          Steps
        </h2>
        <p className="mt-1 mb-0 text-muted">
          Edit wording, tools, critical flags and order before starting the run.
        </p>
      </div>
      {issues.length > 0 ? (
        <div role="alert" className="rounded-control border border-error/60 bg-error/10 px-4 py-3">
          <p className="m-0 font-medium">This procedure is not ready.</p>
          <ul className="mt-1 mb-0 list-disc pl-5 text-small">
            {issues.map((issue) => (
              <li key={`${issue.code}-${issue.message}`}>{issue.message}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <ol className="m-0 flex list-none flex-col gap-3 p-0">
        {steps.map((step, index) => (
          <li key={step.id} className="rounded-card border border-border bg-surface p-4">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-small text-muted">Step {index + 1}</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  aria-label={`Move step ${index + 1} up`}
                  disabled={disabled || index === 0}
                  onClick={() => onChange(moveStep(steps, index, -1))}
                  className="min-h-11 rounded-control border border-border-strong px-3 text-control disabled:opacity-50"
                >
                  Up
                </button>
                <button
                  type="button"
                  aria-label={`Move step ${index + 1} down`}
                  disabled={disabled || index === steps.length - 1}
                  onClick={() => onChange(moveStep(steps, index, 1))}
                  className="min-h-11 rounded-control border border-border-strong px-3 text-control disabled:opacity-50"
                >
                  Down
                </button>
              </div>
            </div>
            <label htmlFor={`${step.id}-text`} className="sr-only">
              Step {index + 1} text
            </label>
            <input
              id={`${step.id}-text`}
              aria-label={`Step ${index + 1} text`}
              value={step.text}
              disabled={disabled}
              className={`${FIELD_CLASS} mt-2`}
              onChange={(event) => onChange(updateStep(steps, index, { text: event.target.value }))}
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {step.tools.map((tool) => (
                <span
                  key={tool}
                  className="inline-flex items-center gap-1 rounded-control border border-border-strong px-2 py-1 text-small"
                >
                  {tool}
                  <button
                    type="button"
                    aria-label={`Remove ${tool} from step ${index + 1}`}
                    disabled={disabled}
                    onClick={() => onChange(removeTool(steps, index, tool))}
                    className="ml-1 text-muted hover:text-error"
                  >
                    ×
                  </button>
                </span>
              ))}
              <ToolAdder
                step={step}
                index={index}
                disabled={disabled}
                onAdd={(tool) => onChange(addTool(steps, index, tool))}
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 text-control">
                <input
                  type="checkbox"
                  aria-label={`Step ${index + 1} critical`}
                  checked={step.critical}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange(updateStep(steps, index, { critical: event.target.checked }))
                  }
                />
                Critical
              </label>
              <label className="flex items-center gap-2 text-control">
                <span className="text-small text-muted">Ordering</span>
                <select
                  aria-label={`Step ${index + 1} ordering`}
                  value={step.ordering}
                  disabled={disabled}
                  className="rounded-control border border-border-strong bg-bg px-2 py-1 text-control"
                  onChange={(event) =>
                    onChange(
                      updateStep(steps, index, {
                        ordering: event.target.value === "unordered_group" ? "unordered_group" : "strict",
                      }),
                    )
                  }
                >
                  <option value="strict">Strict</option>
                  <option value="unordered_group">Any order</option>
                </select>
              </label>
            </div>
          </li>
        ))}
      </ol>
      {steps.length === 0 ? <p className="m-0 text-muted">Compile a SOP to see its steps.</p> : null}
    </section>
  );
}
