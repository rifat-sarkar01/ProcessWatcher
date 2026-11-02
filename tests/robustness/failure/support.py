"""Fault-injecting transport plus the deterministic stage stubs used by the suite.

The transport is the same seam `pw.clients` uses in production, so retries, backoff and
the ledger are exercised for real; only the HTTP socket is replaced. Stage stubs keep
the tests focused on the failing component instead of re-deriving perception outputs.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pw.clients.retry import RetryPolicy
from pw.clients.transport import FilePart, RawResponse
from pw.core.settings import Settings

STEP_IDS = ("stp_01", "stp_02", "stp_03")
FPS = 15.0
FRAMES = 30


def text_body(text: str, *, tokens_in: int = 10, tokens_out: int = 5) -> RawResponse:
    body = {
        "output": [{"content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
    }
    return RawResponse(status=200, headers={}, content=json.dumps(body).encode("utf-8"))


def error_body(
    status: int, message: str, *, headers: Mapping[str, str] | None = None
) -> RawResponse:
    payload = json.dumps({"error": {"message": message}}).encode("utf-8")
    return RawResponse(status=status, headers=dict(headers or {}), content=payload)


@dataclass
class ScriptedTransport:
    """Returns the scripted outcomes in order; the last one repeats."""

    script: Sequence[RawResponse | Exception]
    calls: int = 0
    payloads: list[Mapping[str, Any]] = field(default_factory=list)

    def post_json(self, path: str, payload: Mapping[str, Any], *, timeout_s: float) -> RawResponse:
        self.payloads.append(payload)
        return self._next()

    def post_multipart(
        self,
        path: str,
        fields: Mapping[str, str],
        files: Sequence[FilePart],
        *,
        timeout_s: float,
    ) -> RawResponse:
        self.payloads.append({"fields": dict(fields), "files": len(files)})
        return self._next()

    def _next(self) -> RawResponse:
        outcome = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def retry_policy(delays: list[float] | None = None) -> RetryPolicy:
    return RetryPolicy(
        sleep=(delays.append if delays is not None else (lambda _delay: None)),
        rng=random.Random(7),
    )


def pipeline_settings(
    runs_dir: Path,
    *,
    cap_usd: float = 1.0,
    disable_verifier: bool = False,
    disable_illustrations: bool = False,
) -> Settings:
    return Settings(
        mode="replay",
        meta_api_key="",
        access_code="",
        spend_cap_usd=cap_usd,
        runs_dir=runs_dir,
        disable_verifier=disable_verifier,
        disable_illustrations=disable_illustrations,
    )


# --- deterministic stage stubs (same shapes as tests/pipeline) ---------------


def _step(idx: int, text: str) -> dict[str, Any]:
    return {
        "id": f"stp_{idx:02d}",
        "idx": idx,
        "text": text,
        "action": text,
        "tools": ["cable"] if idx == 2 else [],
        "parts": ["power cable"],
        "ordering": "strict",
        "group_id": None,
        "critical": idx == 1,
        "visual_check": None,
    }


GRAPH: dict[str, Any] = {
    "schema_version": "1.0.0",
    "sop_id": "sop_00000000",
    "title": "Test procedure",
    "source": {"kind": "md", "sha256": "a" * 64},
    "steps": [
        _step(1, "Power the unit down."),
        _step(2, "Unplug the power cable."),
        _step(3, "Remove the cover."),
    ],
    "vocabulary": {"sam_concepts": ["hand", "power cable", "cable"]},
    "warnings": [],
}


def ingest_stub(run: Any) -> dict[str, Any]:
    duration = round(FRAMES / FPS, 4)
    video = run.video.resolve()
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "stage": "ingest",
        "mode": run.mode,
        "source": {"name": video.name, "sha256": "b" * 64, "bytes": video.stat().st_size},
        "analysis": {"path": str(video), "fps": FPS, "frame_count": FRAMES},
        "video": {
            "sha256": "c" * 64,
            "duration_s": duration,
            "analysis_fps": FPS,
            "width": 320,
            "height": 240,
            "frame_count": FRAMES,
        },
        "degraded": False,
    }


def perceive_stub(run: Any) -> dict[str, Any]:
    times = [round(index / FPS, 4) for index in range(FRAMES)]
    tracks: list[dict[str, Any]] = []
    for track_id, concept, left, score in (
        ("trk_001", "hand", 0.4, 0.9),
        ("trk_002", "power cable", 0.45, 0.8),
    ):
        tracks.append(
            {
                "id": track_id,
                "concept": concept,
                "first_t": times[0],
                "last_t": times[-1],
                "frames": [
                    {
                        "frame": index,
                        "t": time,
                        "box": [left, left, left + 0.1, left + 0.1],
                        "score": score,
                    }
                    for index, time in enumerate(times)
                ],
                "source_chunks": ["chk_01"],
            }
        )
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "video": dict(run.artifacts["ingest"]["video"]),
        "tracks": tracks,
    }


def identify_stub(run: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "identities": [
            {
                "track_id": "trk_002",
                "label": "power cable",
                "confidence": 0.9,
                "votes": [{"label": "power cable", "count": 3}],
                "crop_frames": [5, 10, 15],
            }
        ],
    }


def score_stub(run: Any) -> dict[str, Any]:
    timeline = run.artifacts["timeline"]
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "segments": [
            {
                "segment_id": str(segment["id"]),
                "step_probs": {"stp_01": 0.7, "stp_02": 0.15, "stp_03": 0.15, "none": 0.0},
                "observed_tools": [],
                "rationale_short": "fake",
                "flags": [],
            }
            for segment in timeline["segments"]
        ],
    }


def evidence_stub(run: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "available": False,
        "evidence": [],
        "reasons": {},
    }


def handlers(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ingest": ingest_stub,
        "sop_compile": lambda run: dict(GRAPH),
        "perceive": perceive_stub,
        "identify": identify_stub,
        "score": score_stub,
        "evidence": evidence_stub,
    }
    base.update(overrides)
    return base
