"""Illustration prompts: short caption plus the ADR-003 style contract.

The caption is derived from the step action and capped at three words (ADR-003 Q2:
quoted, short, all-caps captions were legible 9/9). The prompt always forbids people,
faces and unlabelled extras so the Wonder QA gate starts from a safe default.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

PROMPT_VERSION = "illustration-v1"
MAX_CAPTION_WORDS = 3
_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "of", "to", "then", "with", "from", "in", "on", "for"}
)
STYLE = (
    "Flat technical schematic illustration, thin dark outlines, light neutral background, "
    "no gradients, no photographs, no text other than the quoted caption. "
    "No faces or people; at most a single gloved hand. Do not invent tools or parts that "
    "are not named."
)


def caption_for(step: Mapping[str, object]) -> str:
    """Deterministic <=3-word uppercase caption from the step's action or text."""
    raw = str(step.get("action") or step.get("text") or "step")
    words = [
        word.upper()
        for word in re.findall(r"[A-Za-z0-9]+", raw)
        if word.casefold() not in _STOPWORDS
    ]
    chosen = words[:MAX_CAPTION_WORDS] or ["STEP"]
    return " ".join(chosen)


def _phrase_list(value: object) -> str:
    if not isinstance(value, (list, tuple)):
        return ""
    return ", ".join(str(item) for item in value)


def build_prompt(
    step: Mapping[str, object],
    *,
    deviation_types: Sequence[str] = (),
    caption: str | None = None,
) -> str:
    text = str(step.get("text") or "").strip()
    tools = _phrase_list(step.get("tools")) or "none listed"
    parts = _phrase_list(step.get("parts")) or "none listed"
    kinds = ", ".join(sorted(set(deviation_types))) or "procedure step"
    label = caption or caption_for(step)
    return (
        f"{STYLE}\n\n"
        f"Show the correct way to perform this step: {text}\n"
        f"Expected tool: {tools}. Expected part: {parts}.\n"
        f"This illustration is for a {kinds} finding.\n"
        f'Write exactly the caption "{label}" inside the image, using clean block letters.'
    )


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


__all__ = [
    "MAX_CAPTION_WORDS",
    "PROMPT_VERSION",
    "STYLE",
    "build_prompt",
    "caption_for",
    "prompt_sha256",
]
