"""Assemble the self-contained audit report.

The builder only joins artifacts: alignment lanes, deviations, hashed evidence,
illustrations and the manifest reference. It owns deterministic ordering, the summary
counts and the `procedure_not_recognized` shape, and it refuses output that violates
`contracts/report.schema.json` or the cross-field invariants.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pw.align.aligner import Alignment
from pw.align.deviations import Deviation
from pw.align.domain_guard import DomainDecision
from pw.data.validate import validate_payload
from pw.evidence.labeling import assert_evidence_kinds

SCHEMA_VERSION = "1.0.0"
DEFAULT_MANIFEST_REF = "manifest.json"
DEFAULT_ILLUSTRATION_REASON = "An illustration was not generated for this run."
NOT_RECOGNIZED_NOTICE = "The video did not match this procedure; no deviations were checked."
_TYPE_ORDER = {"missed": 0, "out_of_order": 1, "wrong_tool": 2}


class ReportError(ValueError):
    """The assembled report would not satisfy the contract."""


@dataclass(frozen=True, slots=True)
class VideoMeta:
    sha256: str
    duration_s: float
    width: int
    height: int

    def to_artifact(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "duration_s": self.duration_s,
            "width": self.width,
            "height": self.height,
        }


def format_mmss(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def _step_text(sop: Mapping[str, Any], step_id: str) -> tuple[int, str]:
    for step in sop.get("steps", []):
        if str(step.get("id")) == step_id:
            return int(step.get("idx", 0)), str(step.get("text", ""))
    return 0, ""


def _template(deviation: Deviation, sop: Mapping[str, Any]) -> str:
    idx, _ = _step_text(sop, deviation.step_id)
    span = f"{format_mmss(deviation.t_start)} to {format_mmss(deviation.t_end)}"
    if deviation.type == "missed":
        return f"Step {idx} was not observed between {span}."
    if deviation.type == "out_of_order":
        related = deviation.relates_to_step_id or "the previous step"
        return f"Step {idx} ran out of order at {span}; it should follow {related}."
    expected = ", ".join(deviation.expected_tools) or "the listed tool"
    observed = ", ".join(deviation.observed_tools) or "another tool"
    return f"Step {idx} needs {expected}; {observed} was used between {span}."


def _ordered_deviations(deviations: Sequence[Deviation]) -> list[Deviation]:
    return sorted(
        deviations,
        key=lambda item: (
            item.t_start,
            item.t_end,
            _TYPE_ORDER.get(item.type, 9),
            item.id,
        ),
    )


def _evidence_by_deviation(
    evidence: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        grouped.setdefault(str(item.get("deviation_id")), []).append(dict(item))
    for items in grouped.values():
        items.sort(key=lambda item: str(item.get("evidence_id", "")))
    return grouped


def _deviation_payload(
    deviation: Deviation,
    *,
    sop: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    explanation: str,
    illustration: Mapping[str, Any] | None,
    illustration_reason: str,
    verifier: Mapping[str, Any] | None,
) -> dict[str, Any]:
    items = [dict(item) for item in evidence]
    payload: dict[str, Any] = {
        "id": deviation.id,
        "type": deviation.type,
        "status": deviation.status,
        "severity": deviation.severity,
        "step_id": deviation.step_id,
        "t_start": deviation.t_start,
        "t_end": deviation.t_end,
        "track_ids": list(deviation.track_ids),
        "confidence": deviation.confidence,
        "margin": deviation.margin,
        "explanation": explanation,
        "verifier": dict(verifier) if verifier is not None else {"ran": False, "agreed": None},
        "evidence": items,
        "evidence_unavailable": not items,
        "illustration": dict(illustration) if illustration is not None else None,
        "illustration_unavailable_reason": None
        if illustration is not None
        else illustration_reason,
    }
    if deviation.relates_to_step_id is not None:
        payload["relates_to_step_id"] = deviation.relates_to_step_id
    if deviation.expected_tools:
        payload["expected_tools"] = list(deviation.expected_tools)
    if deviation.observed_tools:
        payload["observed_tools"] = list(deviation.observed_tools)
    assert_evidence_kinds(items, illustration=payload["illustration"])
    return payload


def _lanes(sop: Mapping[str, Any], alignment: Alignment) -> dict[str, list[dict[str, Any]]]:
    expected = [
        {"step_id": str(step["id"]), "idx": int(step["idx"])}
        for step in sorted(sop.get("steps", []), key=lambda step: int(step["idx"]))
    ]
    observed = [
        {
            "interval_id": interval.id,
            "step_id": interval.step_id,
            "t_start": interval.t_start,
            "t_end": interval.t_end,
        }
        for interval in sorted(alignment.intervals, key=lambda item: (item.t_start, item.id))
    ]
    return {"expected": expected, "observed": observed}


def _summary(deviations: Sequence[Mapping[str, Any]], dropped: int) -> dict[str, Any]:
    counts = {"flagged": 0, "needs_review": 0}
    by_type = {"missed": 0, "out_of_order": 0, "wrong_tool": 0}
    for deviation in deviations:
        if str(deviation["status"]) == "flagged":
            counts["flagged"] += 1
        else:
            counts["needs_review"] += 1
        deviation_type = str(deviation["type"])
        if deviation_type in by_type:
            by_type[deviation_type] += 1
    return {
        "flagged": counts["flagged"],
        "needs_review": counts["needs_review"],
        "dropped": dropped,
        "by_type": by_type,
    }


def build_report(
    *,
    run_id: str,
    created_at: str,
    sop: Mapping[str, Any],
    video: VideoMeta,
    alignment: Alignment,
    deviations: Sequence[Deviation],
    evidence: Sequence[Mapping[str, Any]] = (),
    explanations: Mapping[str, str] | None = None,
    illustrations: Mapping[str, Mapping[str, Any]] | None = None,
    illustration_reasons: Mapping[str, str] | None = None,
    verifiers: Mapping[str, Mapping[str, Any]] | None = None,
    domain: DomainDecision | None = None,
    degraded_stages: Sequence[str] = (),
    dropped: int = 0,
    manifest_ref: str = DEFAULT_MANIFEST_REF,
    contracts_dir: Path | None = None,
) -> dict[str, Any]:
    """Join stage outputs into a contract-valid report."""
    if dropped < 0:
        raise ReportError(f"dropped must be non-negative: {dropped}")
    recognized = domain is None or domain.recognized
    if not recognized:
        status = "not_recognized"
    elif degraded_stages:
        status = "partial"
    else:
        status = "done"

    grouped = _evidence_by_deviation(evidence)
    notes = explanations or {}
    reasons = illustration_reasons or {}
    pictures = illustrations or {}
    checks = verifiers or {}

    payloads: list[dict[str, Any]] = []
    if recognized:
        for deviation in _ordered_deviations(deviations):
            payloads.append(
                _deviation_payload(
                    deviation,
                    sop=sop,
                    evidence=grouped.get(deviation.id, ()),
                    explanation=notes.get(deviation.id) or _template(deviation, sop),
                    illustration=pictures.get(deviation.id),
                    illustration_reason=reasons.get(deviation.id, DEFAULT_ILLUSTRATION_REASON),
                    verifier=checks.get(deviation.id),
                )
            )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "status": status,
        "degraded_stages": list(degraded_stages),
        "sop": dict(sop),
        "video": video.to_artifact(),
        "lanes": _lanes(sop, alignment),
        "deviations": payloads,
        "summary": _summary(payloads, dropped),
        "manifest_ref": manifest_ref,
    }
    if not recognized:
        report["notice"] = (domain.message if domain is not None else None) or (
            NOT_RECOGNIZED_NOTICE
        )

    errors = validate_payload("report", report, contracts_dir)
    if errors:
        raise ReportError("; ".join(errors))
    return report


def write_report(
    report: Mapping[str, Any],
    run_dir: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    contracts_dir: Path | None = None,
) -> Path:
    """Write `report.json` (and the referenced `manifest.json`) into the run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        errors = validate_payload("manifest", dict(manifest), contracts_dir)
        if errors:
            raise ReportError("; ".join(errors))
        (run_dir / DEFAULT_MANIFEST_REF).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    target = run_dir / "report.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target


__all__ = [
    "DEFAULT_ILLUSTRATION_REASON",
    "DEFAULT_MANIFEST_REF",
    "NOT_RECOGNIZED_NOTICE",
    "ReportError",
    "VideoMeta",
    "build_report",
    "format_mmss",
    "write_report",
]
