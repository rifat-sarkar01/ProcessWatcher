import { useId, useState } from "react";

export interface DropzoneProps {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  error?: string | null;
  disabled?: boolean;
  onFile: (file: File) => void;
}

function describeSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Keyboard- and drag-accessible file picker (UI spec §6). */
export function FileDropzone({
  label,
  hint,
  accept,
  file,
  error = null,
  disabled = false,
  onFile,
}: DropzoneProps) {
  const inputId = useId();
  const errorId = useId();
  const [dragging, setDragging] = useState(false);

  function pick(candidate: File | undefined) {
    if (candidate && !disabled) onFile(candidate);
  }

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-control font-medium">
        {label}
      </label>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          pick(event.dataTransfer.files[0]);
        }}
        className={`rounded-control border border-dashed px-4 py-6 text-center ${
          dragging ? "border-accent bg-accent/10" : "border-border-strong bg-surface"
        }`}
      >
        <input
          id={inputId}
          type="file"
          accept={accept}
          disabled={disabled}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
          className="sr-only"
          onChange={(event) => pick(event.target.files?.[0])}
        />
        <p className="m-0 text-control">
          <span className="font-medium">Drop a file here</span> or{" "}
          <label htmlFor={inputId} className="cursor-pointer text-accent underline">
            choose a file
          </label>
        </p>
        <p className="m-0 mt-1 text-small text-muted">{hint}</p>
        {file ? (
          <p role="status" className="m-0 mt-2 text-small">
            Selected: {file.name} · {describeSize(file.size)}
          </p>
        ) : null}
      </div>
      {error ? (
        <p id={errorId} role="alert" className="m-0 text-small text-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
