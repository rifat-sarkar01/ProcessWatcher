"""Prompt for the SOP compiler (T-3.2).

The model only structures text that is already in the SOP: every tool and part it
returns is checked against the source in `compiler.py`, so a hallucination is dropped
rather than trusted.
"""

from __future__ import annotations

from pw.sop.ingest import SopSource

PROMPT_VERSION = "compile-1.0.0"

MAX_PROMPT_CHARS = 16_000
"""Upper bound for the SOP text inside one prompt; longer sources are truncated."""

TRUNCATION_MARKER = "\n…[truncated]"

RULES = """\
- Copy each step from the SOP. Do not add, merge or reorder steps.
- "tools" and "parts" are noun phrases that literally occur in the SOP text.
  Never invent a tool, brand or part that the text does not mention.
- Mark a step "critical" only when its text has an explicit cue: must, never,
  do not, warning, caution or critical.
- Mark a block of steps that may happen in any order as ordering
  "unordered_group" (for example "in either order" or "any order").
- "visual_check" is a short phrase describing what is visible when the step is
  done, or null when the SOP does not say.
- Keep 2 to 40 steps."""

RESPONSE_SHAPE = """\
{"title": "<short procedure title>",
 "steps": [{"text": "<step text>",
            "action": "<verb phrase>",
            "tools": ["<noun phrase>"],
            "parts": ["<noun phrase>"],
            "ordering": "strict" | "unordered_group",
            "critical": false,
            "visual_check": "<phrase>" | null}]}"""


def truncate_text(text: str) -> str:
    """Cut an overlong SOP deterministically so the prompt stays inside budget."""
    if len(text) <= MAX_PROMPT_CHARS:
        return text
    return text[:MAX_PROMPT_CHARS] + TRUNCATION_MARKER


def prompt_for(source: SopSource) -> str:
    """Build the single compile prompt; deterministic for a given source."""
    return "\n".join(
        [
            f"SOP COMPILER {PROMPT_VERSION}",
            "",
            "Compile the procedure below into strict JSON. The SAM vocabulary must",
            'always contain the generic concept "hand".',
            "",
            "Rules:",
            RULES,
            "",
            "Return this JSON shape and nothing else:",
            RESPONSE_SHAPE,
            "",
            "SOP:",
            truncate_text(source.text).strip(),
        ]
    )
