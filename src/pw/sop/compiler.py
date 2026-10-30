"""SOP compiler: strict-JSON step graph with grounding, repair and explicit cues.

The model is a callable (`Compiler`): production passes a Muse Wonder writer through
`pw.clients`, tests pass a fake. Everything that decides what reaches the aligner is
deterministic here — IDs, ordering groups, critical flags, the SAM vocabulary and the
grounding check that drops any tool or part the SOP text does not mention.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any

from pw.data.validate import validate_payload
from pw.sop.ingest import SopSource
from pw.sop.prompts import MAX_PROMPT_CHARS, PROMPT_VERSION, prompt_for

MAX_RETRIES = 2
MAX_ATTEMPTS = MAX_RETRIES + 1
MAX_STEPS = 40
MIN_STEPS = 2
MAX_CONCEPTS = 24
MAX_TEXT_CHARS = 400
MAX_TITLE_CHARS = 120
MAX_VISUAL_CHARS = 200

GENERIC_CONCEPTS = ("hand",)
"""Concepts that need no literal mention: the SOP vocabulary always includes `hand`."""

Compiler = Callable[[str], str]

_CRITICAL_CUE = re.compile(r"\b(must|never|do not|don't|warning|caution|critical)\b", re.IGNORECASE)
_ANY_ORDER_CUE = re.compile(
    r"\b(?:in\s+)?(?:any\s+order|any\s+sequence|either\s+order|order\s+does\s+not\s+matter)\b",
    re.IGNORECASE,
)
# "either order" compares two options, so the cue also covers the step just before it.
_PAIR_ORDER_CUE = re.compile(r"\bin\s+either\s+order\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


class CompileError(RuntimeError):
    """The model could not produce a valid step graph inside the attempt budget."""

    def __init__(self, message: str, *, attempts: int, issues: Sequence[str]) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.issues = tuple(issues)


class _Rejected(ValueError):
    """One response was unusable; the message lists the reasons for the repair."""

    def __init__(self, errors: Sequence[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = tuple(errors)


@dataclass(frozen=True, slots=True)
class CompileResult:
    graph: dict[str, Any]
    attempts: int
    cached: bool = False


def normalise_phrase(value: str) -> str:
    return _WHITESPACE.sub(" ", value.strip().lower())


def cache_key(source: SopSource) -> str:
    """Stable per (prompt version, source) so replay can skip the model call."""
    digest = hashlib.sha256()
    digest.update(PROMPT_VERSION.encode("utf-8"))
    digest.update(b"\0")
    digest.update(source.sha256.encode("utf-8"))
    digest.update(b"\0")
    digest.update(source.text.encode("utf-8"))
    return digest.hexdigest()


def is_grounded(phrase: str, source_text: str) -> bool:
    normalised = normalise_phrase(phrase)
    if not normalised:
        return False
    if normalised in GENERIC_CONCEPTS:
        return True
    return normalised in source_text


def _parse_response(raw: str) -> Any:
    text = _FENCE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise _Rejected([f"invalid_json: {exc.msg} at line {exc.lineno}"]) from exc


def _ground_list(
    values: Any,
    source_text: str,
    kind: str,
    warnings: list[str],
) -> list[str]:
    if not isinstance(values, list):
        return []
    kept: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        phrase = normalise_phrase(value)
        if not phrase or phrase in kept:
            continue
        if is_grounded(phrase, source_text):
            kept.append(phrase)
        else:
            warnings.append(f"dropped ungrounded {kind}: {phrase}")
    return kept


def _raw_steps(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise _Rejected(["sop: the response must be a JSON object"])
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise _Rejected(["sop: steps: expected an array"])
    if len(steps) < MIN_STEPS:
        raise _Rejected([f"sop: steps: at least {MIN_STEPS} steps are required"])
    parsed: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or not isinstance(step.get("text"), str):
            raise _Rejected([f"sop: steps[{index}]: expected an object with text"])
        parsed.append(step)
    return parsed


def _build_graph(
    source: SopSource,
    payload: Any,
    *,
    warnings: list[str],
) -> dict[str, Any]:
    raw_steps = _raw_steps(payload)
    if len(raw_steps) > MAX_STEPS:
        warnings.append(f"kept the first {MAX_STEPS} of {len(raw_steps)} steps")
        raw_steps = raw_steps[:MAX_STEPS]

    source_text = normalise_phrase(source.text)
    unordered = [
        step.get("ordering") == "unordered_group" or bool(_ANY_ORDER_CUE.search(str(step["text"])))
        for step in raw_steps
    ]
    for index, step in enumerate(raw_steps):
        if index > 0 and _PAIR_ORDER_CUE.search(str(step["text"])):
            unordered[index - 1] = True

    steps: list[dict[str, Any]] = []
    next_group = 1
    for index, step in enumerate(raw_steps, start=1):
        text = str(step["text"]).strip()
        if len(text) > MAX_TEXT_CHARS:
            warnings.append(f"step {index} truncated to {MAX_TEXT_CHARS} characters")
            text = text[:MAX_TEXT_CHARS]
        visual = step.get("visual_check")
        cleaned = visual.strip() if isinstance(visual, str) else ""
        visual_check = cleaned[:MAX_VISUAL_CHARS] if cleaned else None
        group_id: str | None = None
        if unordered[index - 1]:
            if index > 1 and unordered[index - 2]:
                group_id = steps[-1]["group_id"]
            else:
                group_id = f"grp_{next_group:02d}"
                next_group += 1
        tools = _ground_list(step.get("tools"), source_text, "tool", warnings)
        parts = _ground_list(step.get("parts"), source_text, "part", warnings)
        steps.append(
            {
                "id": f"stp_{index:02d}",
                "idx": index,
                "text": text,
                "action": str(step.get("action") or "do").strip()[:60] or "do",
                "tools": tools,
                "parts": parts,
                "ordering": "unordered_group" if group_id else "strict",
                "group_id": group_id,
                "critical": bool(_CRITICAL_CUE.search(text)),
                "visual_check": visual_check,
            }
        )

    title = str(payload.get("title") or "").strip()[:MAX_TITLE_CHARS]
    source_block: dict[str, Any] = {"kind": source.kind, "sha256": source.sha256}
    if source.page_count is not None:
        source_block["pages"] = source.page_count

    graph: dict[str, Any] = {
        "schema_version": "1.0.0",
        "sop_id": f"sop_{source.sha256[:8]}",
        "title": title,
        "source": source_block,
        "steps": steps,
        "vocabulary": {"sam_concepts": _vocabulary(steps), "zones": []},
    }
    unique_warnings = list(dict.fromkeys(warnings))
    if unique_warnings:
        graph["warnings"] = unique_warnings

    errors = validate_payload("sop", graph)
    if errors:
        raise _Rejected(errors)
    return graph


def _vocabulary(steps: Sequence[dict[str, Any]]) -> list[str]:
    concepts: list[str] = list(GENERIC_CONCEPTS)
    for step in steps:
        for phrase in [*step["tools"], *step["parts"]]:
            if phrase not in concepts:
                concepts.append(phrase)
    return concepts[:MAX_CONCEPTS]


def _repair_suffix(issues: Sequence[str]) -> str:
    lines = "\n".join(f"- {issue}" for issue in issues)
    return (
        "\n\nThe previous response was rejected:\n"
        f"{lines}\n"
        "Return corrected JSON only, following every rule above."
    )


def compile_sop(
    source: SopSource,
    *,
    compiler: Compiler,
    cache: MutableMapping[str, str] | None = None,
    max_retries: int = MAX_RETRIES,
) -> CompileResult:
    """Compile one SOP source into a contract-valid step graph.

    With `cache` the final graph is stored under `cache_key`; a hit returns without
    calling the model, which is what replay mode and repeated runs rely on.
    """
    if not source.text.strip():
        issue = "needs_vision" if source.needs_vision else "empty_source"
        raise CompileError(
            f"SOP cannot be compiled from text: {issue}",
            attempts=0,
            issues=(issue,),
        )

    key = cache_key(source)
    if cache is not None:
        stored = cache.get(key)
        if stored is not None:
            try:
                graph = json.loads(stored)
            except json.JSONDecodeError:
                graph = None
            if isinstance(graph, dict) and not validate_payload("sop", graph):
                return CompileResult(graph=graph, attempts=0, cached=True)

    prompt = prompt_for(source)
    warnings: list[str] = []
    if len(source.text) > MAX_PROMPT_CHARS:
        warnings.append(f"source truncated to {MAX_PROMPT_CHARS} characters in the prompt")

    attempts = max_retries + 1
    issues: tuple[str, ...] = ()
    for attempt in range(1, attempts + 1):
        raw = compiler(prompt if attempt == 1 else prompt + _repair_suffix(issues))
        try:
            payload = _parse_response(raw)
            graph = _build_graph(source, payload, warnings=list(warnings))
        except _Rejected as rejected:
            issues = rejected.errors
            continue
        if cache is not None:
            cache[key] = json.dumps(graph, sort_keys=True)
        return CompileResult(graph=graph, attempts=attempt)

    raise CompileError(
        f"SOP compilation failed after {attempts} attempts: {'; '.join(issues)}",
        attempts=attempts,
        issues=issues,
    )


__all__ = [
    "MAX_ATTEMPTS",
    "MAX_RETRIES",
    "CompileError",
    "CompileResult",
    "Compiler",
    "cache_key",
    "compile_sop",
    "is_grounded",
    "normalise_phrase",
    "prompt_for",
]
