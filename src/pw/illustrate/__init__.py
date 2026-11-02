"""Illustration generation: Muse Image diagrams, QA and watermarking (FR-10)."""

from pw.illustrate.generator import (
    ILLUSTRATION_KIND,
    Illustration,
    IllustrationSet,
    client_caller,
    generate_illustrations,
    illustrations_disabled,
)
from pw.illustrate.prompts import PROMPT_VERSION, build_prompt, caption_for

__all__ = [
    "ILLUSTRATION_KIND",
    "PROMPT_VERSION",
    "Illustration",
    "IllustrationSet",
    "build_prompt",
    "caption_for",
    "client_caller",
    "generate_illustrations",
    "illustrations_disabled",
]
