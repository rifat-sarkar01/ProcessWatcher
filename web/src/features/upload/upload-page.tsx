import { useState } from "react";

import { ApiError } from "../../api";
import { Banner } from "../../ui/states";

import { createUploadApi, type UploadApi } from "./client";
import { FileDropzone } from "./dropzone";
import { StepEditor } from "./step-editor";
import { validateSteps, type CompilePreview, type StepDraft } from "./types";

const VIDEO_ACCEPT = ".mp4,.mov,.webm,.mkv,video/*";
const SOP_ACCEPT = ".md,.txt,.pdf,text/markdown,text/plain,application/pdf";
const MAX_BYTES = 500 * 1024 * 1024;
const TEXT_SUFFIXES = [".md", ".txt"];

export interface UploadPageProps {
  api?: UploadApi;
  accessCode?: string | null;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  initialSteps?: StepDraft[];
  onStarted?: (runId: string) => void;
}

function suffix(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

/**
 * Upload + SOP review (`02_AppFlow` §2.1–2.2): drop the video and SOP, preview the
 * compiled step graph, edit it, then start the run. Validation gates Start; API errors
 * surface by typed code (401/413/422) through the shared `ApiError`.
 */
export function UploadPage({
  api,
  accessCode = null,
  baseUrl = "",
  fetchImpl,
  initialSteps = [],
  onStarted,
}: UploadPageProps) {
  const client = api ?? createUploadApi({ baseUrl, accessCode, fetchImpl });
  const [video, setVideo] = useState<File | null>(null);
  const [sopFile, setSopFile] = useState<File | null>(null);
  const [sopText, setSopText] = useState("");
  const [steps, setSteps] = useState<StepDraft[]>(initialSteps);
  const [preview, setPreview] = useState<CompilePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [sopError, setSopError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  const issues = validateSteps(steps);
  const canStart = video !== null && preview !== null && issues.length === 0 && !busy;

  function acceptVideo(file: File) {
    if (!file.type.startsWith("video/") && !VIDEO_ACCEPT.includes(suffix(file.name))) {
      setVideoError("That file type isn't supported. Use mp4, mov, webm or mkv.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setVideoError("That upload is larger than the 500 MB limit.");
      return;
    }
    setVideoError(null);
    setVideo(file);
  }

  async function acceptSop(file: File) {
    if (file.size > MAX_BYTES) {
      setSopError("That SOP is larger than the 500 MB limit.");
      return;
    }
    setSopError(null);
    setSopFile(file);
    if (TEXT_SUFFIXES.includes(suffix(file.name))) {
      try {
        setSopText(await file.text());
      } catch {
        setSopError("That SOP file could not be read.");
      }
    } else {
      setSopText("");
    }
  }

  async function compile() {
    setError(null);
    if (!sopFile && !sopText.trim()) {
      setError("Attach a SOP file or paste the steps first.");
      return;
    }
    setBusy(true);
    try {
      const result = await client.compile(
        sopFile && !TEXT_SUFFIXES.includes(suffix(sopFile.name))
          ? { file: sopFile }
          : { text: sopText },
      );
      setPreview(result);
      setSteps(result.step_graph.steps);
      setRunId(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The SOP could not be compiled.");
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!video) return;
    setError(null);
    setBusy(true);
    try {
      const started = await client.startRun({
        video,
        sop: sopFile,
        sopText: sopFile ? null : sopText,
        stepGraph: preview ? { ...preview.step_graph, steps } : null,
      });
      setRunId(started.run_id);
      onStarted?.(started.run_id);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The run could not be started.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="upload-heading" className="flex flex-col gap-4">
        <div>
          <h1 id="upload-heading" className="m-0 text-h2 font-semibold">
            Check a procedure
          </h1>
          <p className="mt-2 mb-0 text-muted">
            Upload the recording and its written SOP. Steps are compiled first so you can
            correct them before any footage is analysed.
          </p>
        </div>
        <FileDropzone
          label="Procedure video"
          hint="MP4, MOV, WEBM or MKV · up to 3 minutes · 500 MB"
          accept={VIDEO_ACCEPT}
          file={video}
          error={videoError}
          disabled={busy}
          onFile={acceptVideo}
        />
        <FileDropzone
          label="Written SOP"
          hint="Markdown, plain text or PDF"
          accept={SOP_ACCEPT}
          file={sopFile}
          error={sopError}
          disabled={busy}
          onFile={(file) => {
            void acceptSop(file);
          }}
        />
        <div className="flex flex-col gap-2">
          <label htmlFor="sop-text" className="text-control font-medium">
            SOP text
          </label>
          <textarea
            id="sop-text"
            aria-label="SOP text"
            value={sopText}
            disabled={busy}
            rows={6}
            placeholder="1. Power the unit down.&#10;2. Unplug the power cable."
            className="w-full rounded-control border border-border-strong bg-bg px-3 py-2 text-control text-fg"
            onChange={(event) => {
              setSopText(event.target.value);
              setSopFile(null);
            }}
          />
          <div>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                void compile();
              }}
              className="min-h-11 rounded-control bg-accent px-4 text-control font-medium text-accent-ink disabled:opacity-50"
            >
              Compile SOP
            </button>
          </div>
        </div>
        {error ? <Banner tone="error">{error}</Banner> : null}
      </section>

      {preview || steps.length > 0 ? (
        <section aria-labelledby="preview-heading" className="flex flex-col gap-3">
          <div>
            <h2 id="preview-heading" className="m-0 text-h3 font-semibold">
              {preview?.step_graph.title ?? "Review steps"}
            </h2>
            {preview ? (
              <p className="mt-1 mb-0 text-small text-muted">
                {preview.step_graph.steps.length} steps · vocabulary:{" "}
                {preview.vocabulary.join(", ")}
              </p>
            ) : null}
            {preview && preview.warnings.length > 0 ? (
              <ul className="mt-2 mb-0 list-disc pl-5 text-small text-dev-order">
                {preview.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </div>
          <StepEditor steps={steps} onChange={setSteps} disabled={busy} />
          <div className="flex items-center gap-4">
            <button
              type="button"
              disabled={!canStart}
              onClick={() => {
                void start();
              }}
              className="min-h-11 rounded-control bg-accent px-4 text-control font-medium text-accent-ink disabled:opacity-50"
            >
              Start run
            </button>
            {!video ? <p className="m-0 text-small text-muted">Add the video to start.</p> : null}
            {runId ? (
              <p role="status" className="m-0 text-small">
                Run started: <span className="font-mono">{runId}</span>
              </p>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
