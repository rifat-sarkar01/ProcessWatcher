import type { Report } from "../../src/types/generated/report";

const HEX = "a".repeat(64);

const STEP_TEXT = [
  "Power the unit down.",
  "Unplug the power cable.",
  "Remove the cover.",
] as const;

export const COMPILE_RESPONSE = {
  step_graph: {
    schema_version: "1.0.0",
    sop_id: "sop_01234567",
    title: "Cable check",
    source: { kind: "pasted", sha256: HEX },
    steps: STEP_TEXT.map((text, index) => ({
      id: `stp_0${index + 1}`,
      idx: index + 1,
      text,
      action: text,
      tools: index === 1 ? ["hand"] : ["screwdriver"],
      parts: index === 2 ? ["cover"] : ["power cable"],
      ordering: "strict",
      group_id: null,
      critical: index === 1,
      visual_check: null,
    })),
    vocabulary: { sam_concepts: ["hand", "screwdriver"] },
    warnings: [],
  },
  vocabulary: ["hand", "screwdriver"],
  warnings: [],
};

export const REPORT: Report = {
  schema_version: "1.0.0",
  run_id: "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ",
  created_at: "2026-11-02T00:00:00Z",
  status: "done",
  degraded_stages: [],
  sop: COMPILE_RESPONSE.step_graph,
  video: { sha256: HEX, duration_s: 30, width: 640, height: 360 },
  lanes: {
    expected: [
      { step_id: "stp_01", idx: 1 },
      { step_id: "stp_02", idx: 2 },
      { step_id: "stp_03", idx: 3 },
    ],
    observed: [
      { interval_id: "int_01", step_id: "stp_01", t_start: 0, t_end: 8 },
      { interval_id: "int_02", step_id: "stp_03", t_start: 9, t_end: 22 },
    ],
  },
  deviations: [
    {
      id: "dev_001",
      type: "missed",
      status: "flagged",
      severity: "high",
      step_id: "stp_02",
      relates_to_step_id: null,
      t_start: 8,
      t_end: 9,
      track_ids: ["trk_001"],
      confidence: 0.86,
      margin: 0.61,
      explanation: "Step 2 was not observed between step 1 and step 3.",
      verifier: { ran: true, agreed: true, note: "confirmed" },
      expected_tools: ["hand"],
      observed_tools: [],
      evidence: [
        {
          evidence_id: "evd_001",
          deviation_id: "dev_001",
          kind: "evidence",
          source_sha256: HEX,
          frame_index: 120,
          t: 8,
          render_version: "render-1.0.0",
          params_hash: HEX,
          output_path: "evidence/evd_001.png",
          output_sha256: HEX,
          phash: "0123456789abcdef",
          track_ids: ["trk_001"],
        },
      ],
      evidence_unavailable: false,
      illustration: {
        id: "ill_001",
        kind: "illustration",
        path: "illustrations/ill_001.png",
        sha256: HEX,
        watermark: true,
        qa: { verdict: "pass", attempts: 1 },
      },
      illustration_unavailable_reason: null,
    },
  ],
  summary: {
    flagged: 1,
    needs_review: 0,
    dropped: 0,
    by_type: { missed: 1, out_of_order: 0, wrong_tool: 0 },
  },
  manifest_ref: "manifest.json",
};

export const STAGE_EVENTS = [
  "ingest",
  "sop_compile",
  "perceive",
  "timeline",
  "identify",
  "score",
  "align",
  "deviations",
  "verify",
  "evidence",
  "illustrate",
  "report",
]
  .map(
    (stage) =>
      `event: stage\ndata: ${JSON.stringify({
        stage,
        status: "done",
        pct: 100,
        elapsed_s: 1,
        cost_usd: 0,
      })}\n\n`,
  )
  .join("") + 'event: done\ndata: {"status":"done"}\n\n';
