"""Load the frozen threshold config (T-3.10) for the pipeline.

`config/thresholds.json` is optional while calibrating: without it the documented
defaults apply. Once T-3.10 freezes the file, every run records its hash in the
manifest and the deviation stage uses the calibrated values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pw.align.deviations import DeviationParams
from pw.data.schemas import load_json

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "thresholds.json"


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_PATH
    if not target.is_file():
        return {}
    payload = load_json(target)
    return payload if isinstance(payload, dict) else {}


def deviation_params(payload: dict[str, Any] | None = None) -> DeviationParams:
    values = (payload or {}).get("deviation", {})
    if not isinstance(values, dict):
        return DeviationParams()
    return DeviationParams(
        tau_miss=float(values.get("tau_miss", 0.25)),
        tau_flag=float(values.get("tau_flag", 0.7)),
        tau_review=float(values.get("tau_review", 0.4)),
        wrong_tool_fraction=float(values.get("wrong_tool_fraction", 0.5)),
        identity_confidence=float(values.get("wrong_tool_conf", 0.6)),
    )


__all__ = ["DEFAULT_PATH", "deviation_params", "load_thresholds"]
