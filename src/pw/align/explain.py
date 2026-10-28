"""Grounded explanation writer: constrained prompt, strict validator, template fallback.

The model only writes prose; compliance comes from the aligner. Every explanation is
checked against the deviation's own data: at most two sentences and 40 words, the step
number must be cited, timestamps must be within 0.5 s of a recorded time, and tool
mentions must come from the procedure vocabulary. Invalid text is retried at most twice
and then replaced by a deterministic template.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from pw.align.deviations import Deviation

MAX_SENTENCES = 2
MAX_WORDS = 40
MAX_CHARS = 400
MAX_RETRIES = 2
MAX_ATTEMPTS = MAX_RETRIES + 1
TIME_TOLERANCE_S = 0.5

ExplanationSource = Literal["model", "template"]
Writer = Callable[[str], str]

_TIME = re.compile(r"(?<![\d:])(\d{1,3}):([0-5]\d)(?:\.(\d{1,3}))?(?![\d:])")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")
_TOOL_STOPWORDS = "between|at|on|to|from|and|while|instead|step|the|a|an|this|that|it|there"
_TOOL_AFTER_VERB = re.compile(
    r"\b(?:with|using|use[ds]?|needs?|needed|requires?)\s+(?:the\s+|an?\s+)?"
    rf"(?!(?:{_TOOL_STOPWORDS})\b)"
    r"([a-z][a-z \-]{2,30}?)(?=\s*(?:[.,;:!?]|\s+(?:to|on|at|from|between|and|"
    r"while|instead|was|is)\b|$))",
    re.IGNORECASE,
)
_TOOL_BEFORE_USED = re.compile(
    r"\b(?:the\s+|an?\s+)?([a-z][a-z0-9 \-]{2,30}?)\s+(?:was|is)\s+used\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Explanation:
    text: str
    source: ExplanationSource
    attempts: int
    issues: tuple[str, ...] = ()


def format_time(seconds: float) -> str:
    total = max(0.0, seconds)
    minutes = int(total // 60)
    remainder = total - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def _parse_time(minutes: str, seconds: str, fraction: str | None) -> float:
    value = float(int(minutes) * 60 + int(seconds))
    if fraction:
        value += float(f"0.{fraction}")
    return value


def mentioned_times(text: str) -> tuple[float, ...]:
    return tuple(
        _parse_time(match.group(1), match.group(2), match.group(3))
        for match in _TIME.finditer(text)
    )


def mentioned_tools(text: str) -> tuple[str, ...]:
    phrases = {match.group(1).strip().lower() for match in _TOOL_AFTER_VERB.finditer(text)}
    phrases.update(match.group(1).strip().lower() for match in _TOOL_BEFORE_USED.finditer(text))
    return tuple(sorted(phrases))


def count_sentences(text: str) -> int:
    return len(_SENTENCE_END.findall(text))


def _normalise_tool(name: str) -> str:
    return " ".join(name.lower().split())


def validate_explanation(
    text: str,
    *,
    step_index: int,
    step_id: str,
    data_times: Sequence[float],
    vocabulary: Sequence[str],
) -> tuple[str, ...]:
    """Return issue codes (empty means the text may be shown to a reviewer)."""
    issues: list[str] = []
    stripped = text.strip()
    if not stripped:
        return ("empty",)
    if len(stripped) > MAX_CHARS:
        issues.append(f"too_long:{len(stripped)}")
    if count_sentences(stripped) > MAX_SENTENCES:
        issues.append(f"too_many_sentences:{count_sentences(stripped)}")
    word_count = len(stripped.split())
    if word_count > MAX_WORDS:
        issues.append(f"too_many_words:{word_count}")

    if f"step {step_index}" not in stripped.lower() and step_id not in stripped:
        issues.append("missing_step")

    for value in mentioned_times(stripped):
        if not any(abs(value - allowed) <= TIME_TOLERANCE_S for allowed in data_times):
            issues.append(f"unknown_time:{format_time(value)}")

    allowed_tools = {_normalise_tool(tool) for tool in vocabulary}
    for tool in mentioned_tools(stripped):
        if tool not in allowed_tools:
            issues.append(f"unknown_tool:{tool}")
    return tuple(issues)


def step_index_of(step_id: str) -> int:
    match = re.search(r"(\d+)$", step_id)
    return int(match.group(1)) if match else 0


def make_prompt(
    deviation: Deviation,
    *,
    step_index: int,
    step_text: str = "",
    data_times: Sequence[float],
    vocabulary: Sequence[str],
) -> str:
    """Constrained prompt listing exactly the facts and vocabulary the answer may use."""
    times = ", ".join(format_time(value) for value in data_times)
    tools = ", ".join(vocabulary) if vocabulary else "none"
    observed = ", ".join(deviation.observed_tools) or "none"
    expected = ", ".join(deviation.expected_tools) or "none"
    lines = [
        "Write an audit note for one SOP deviation.",
        f"Deviation type: {deviation.type}.",
        f"Step: {step_index} ({deviation.step_id}).",
    ]
    if step_text:
        lines.append(f"Step text: {step_text}")
    lines.extend(
        [
            f"Expected tools: {expected}.",
            f"Observed tools: {observed}.",
            f"Times you may cite: {times} (mm:ss).",
            f"Tools you may name: {tools}.",
            "Rules: at most 2 sentences, at most 40 words, cite the step number, "
            "cite only the times listed, name only the tools listed, no speculation.",
            "Answer with the note only.",
        ]
    )
    return "\n".join(lines)


def template_explanation(deviation: Deviation, *, step_index: int) -> str:
    """Deterministic fallback that always passes the validator."""
    span = f"{format_time(deviation.t_start)} to {format_time(deviation.t_end)}"
    if deviation.type == "missed":
        return f"Step {step_index} was not observed between {span}."
    if deviation.type == "out_of_order":
        related = step_index_of(deviation.relates_to_step_id or "")
        if related:
            return f"Step {step_index} ran out of order at {span}; it should follow step {related}."
        return f"Step {step_index} ran out of order at {span}."
    expected = ", ".join(deviation.expected_tools) or "the listed tool"
    observed = ", ".join(deviation.observed_tools) or "a different tool"
    return f"Step {step_index} needs {expected}; {observed} was used between {span}."


def explain_deviation(
    deviation: Deviation,
    *,
    writer: Writer,
    vocabulary: Sequence[str],
    step_index: int | None = None,
    step_text: str = "",
    extra_times: Sequence[float] = (),
) -> Explanation:
    """Ask the writer for a note; validate, retry at most twice, then fall back."""
    index = step_index if step_index is not None else step_index_of(deviation.step_id)
    data_times = tuple(dict.fromkeys([deviation.t_start, deviation.t_end, *extra_times]))
    prompt = make_prompt(
        deviation,
        step_index=index,
        step_text=step_text,
        data_times=data_times,
        vocabulary=vocabulary,
    )
    issues: tuple[str, ...] = ()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = writer(prompt)
        except Exception:  # any model or transport failure degrades to the template
            issues = ("writer_error",)
            continue
        issues = validate_explanation(
            text,
            step_index=index,
            step_id=deviation.step_id,
            data_times=data_times,
            vocabulary=vocabulary,
        )
        if not issues:
            return Explanation(text.strip(), "model", attempt)
    return Explanation(
        template_explanation(deviation, step_index=index),
        "template",
        MAX_ATTEMPTS,
        issues,
    )


__all__ = [
    "MAX_ATTEMPTS",
    "MAX_RETRIES",
    "MAX_SENTENCES",
    "MAX_WORDS",
    "TIME_TOLERANCE_S",
    "Explanation",
    "count_sentences",
    "explain_deviation",
    "format_time",
    "make_prompt",
    "mentioned_times",
    "mentioned_tools",
    "step_index_of",
    "template_explanation",
    "validate_explanation",
]
