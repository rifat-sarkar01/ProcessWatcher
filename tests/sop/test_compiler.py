"""SOP compiler tests: grounding, repair, explicit cues, ordering groups, cache."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest

from pw.sop.compiler import (
    MAX_ATTEMPTS,
    CompileError,
    compile_sop,
    prompt_for,
)
from pw.sop.ingest import SopSource
from pw.sop.prompts import PROMPT_VERSION

SHA = "0123456789abcdef" * 4

SOP_TEXT = """# SSD swap

1. Power the PC down and unplug the power cable.
2. Remove the two rear thumbscrews.
3. Unplug the SATA data cable from the old SSD.
4. Unplug the SATA power cable from the old SSD.
5. Slide the new SSD into the bay.
6. Reconnect the SATA data and power cables in any order.
7. Close the side panel.
"""


def source(text: str = SOP_TEXT, *, needs_vision: bool = False) -> SopSource:
    return SopSource(
        kind="md",
        text=text,
        sha256=SHA,
        page_count=1 if needs_vision else None,
        needs_vision=needs_vision,
    )


def step(
    text: str,
    *,
    tools: Sequence[str] = (),
    parts: Sequence[str] = (),
    ordering: str = "strict",
    critical: bool = False,
    visual_check: str | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "action": "do",
        "tools": list(tools),
        "parts": list(parts),
        "ordering": ordering,
        "critical": critical,
        "visual_check": visual_check,
    }


def response(steps: Sequence[dict[str, Any]], title: str = "SSD swap") -> str:
    return json.dumps({"title": title, "steps": list(steps)})


DEFAULT_STEPS = [
    step("Power the PC down and unplug the power cable.", tools=["hand"], parts=["power cable"]),
    step("Remove the two rear thumbscrews.", tools=["hand"], parts=["thumbscrews"]),
    step("Unplug the SATA data cable from the old SSD.", parts=["sata data cable"]),
    step("Unplug the SATA power cable from the old SSD.", parts=["sata power cable"]),
    step("Slide the new SSD into the bay.", tools=["hand"], parts=["new ssd"]),
    step(
        "Reconnect the SATA data and power cables in any order.",
        parts=["sata data cable", "sata power cable"],
        ordering="unordered_group",
    ),
    step("Close the side panel.", parts=["side panel"]),
]


class FakeCompiler:
    """Returns queued responses and records the prompts it saw."""

    def __init__(self, responses: Sequence[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("compiler called more times than expected")
        return self.responses.pop(0)


def compile_ok(
    steps: Sequence[dict[str, Any]] = DEFAULT_STEPS,
    *,
    text: str = SOP_TEXT,
    cache: Any = None,
) -> tuple[Any, FakeCompiler]:
    compiler = FakeCompiler([response(steps)])
    result = compile_sop(source(text), compiler=compiler, cache=cache)
    return result, compiler


@pytest.mark.unit
def test_compiles_a_grounded_step_graph() -> None:
    result, _ = compile_ok()
    graph = result.graph

    assert graph["sop_id"] == "sop_01234567"
    assert graph["source"] == {"kind": "md", "sha256": SHA}
    assert graph["title"] == "SSD swap"
    assert [item["id"] for item in graph["steps"]] == [
        "stp_01",
        "stp_02",
        "stp_03",
        "stp_04",
        "stp_05",
        "stp_06",
        "stp_07",
    ]
    assert [item["idx"] for item in graph["steps"]] == list(range(1, 8))
    assert graph["vocabulary"]["sam_concepts"][0] == "hand"
    assert result.attempts == 1
    assert result.cached is False


@pytest.mark.unit
def test_every_step_carries_the_compiled_fields() -> None:
    result, _ = compile_ok()

    first = result.graph["steps"][0]
    assert first["text"] == DEFAULT_STEPS[0]["text"]
    assert first["action"] == "do"
    assert first["critical"] is False
    assert first["group_id"] is None


@pytest.mark.unit
def test_invalid_json_is_repaired_on_the_next_attempt() -> None:
    compiler = FakeCompiler(["not json at all", response(DEFAULT_STEPS)])

    result = compile_sop(source(), compiler=compiler)

    assert result.attempts == 2
    assert result.graph["steps"]
    assert "rejected" in compiler.prompts[1]
    assert "invalid_json" in compiler.prompts[1]


@pytest.mark.unit
def test_gives_up_after_the_attempt_budget() -> None:
    compiler = FakeCompiler(["nope"] * MAX_ATTEMPTS)

    with pytest.raises(CompileError) as caught:
        compile_sop(source(), compiler=compiler)

    assert caught.value.attempts == MAX_ATTEMPTS
    assert any(issue.startswith("invalid_json") for issue in caught.value.issues)
    assert len(compiler.prompts) == MAX_ATTEMPTS


@pytest.mark.unit
def test_schema_invalid_response_is_sent_back_for_repair() -> None:
    compiler = FakeCompiler([response(DEFAULT_STEPS, title=""), response(DEFAULT_STEPS)])

    result = compile_sop(source(), compiler=compiler)

    assert result.attempts == 2
    assert "sop:" in compiler.prompts[1]
    assert "title" in compiler.prompts[1]


@pytest.mark.unit
def test_hallucinated_tool_is_dropped_with_a_warning() -> None:
    steps = [
        step("Power the PC down.", tools=["phillips screwdriver"], parts=["power cable"]),
        step("Close the side panel.", tools=["hand"], parts=["side panel"]),
    ]

    result, _ = compile_ok(steps)

    tools = result.graph["steps"][0]["tools"]
    assert tools == []
    assert "phillips screwdriver" not in result.graph["vocabulary"]["sam_concepts"]
    assert any("phillips screwdriver" in warning for warning in result.graph["warnings"])


@pytest.mark.unit
def test_critical_follows_explicit_cues_only() -> None:
    steps = [
        step("You must unplug the power cable.", tools=["hand"], parts=["power cable"]),
        step("Close the side panel.", parts=["side panel"], critical=True),
    ]

    result, _ = compile_ok(steps)

    assert result.graph["steps"][0]["critical"] is True
    assert result.graph["steps"][1]["critical"] is False


@pytest.mark.unit
def test_any_order_cue_creates_one_shared_group() -> None:
    steps = [
        step(
            "Unplug the SATA data cable.",
            parts=["sata data cable"],
            ordering="unordered_group",
        ),
        step(
            "Unplug the SATA power cable.",
            parts=["sata power cable"],
            ordering="unordered_group",
        ),
        step("Close the side panel.", parts=["side panel"]),
    ]

    result, _ = compile_ok(steps)

    first, second, third = result.graph["steps"]
    assert first["ordering"] == second["ordering"] == "unordered_group"
    assert first["group_id"] == second["group_id"] == "grp_01"
    assert third["ordering"] == "strict"
    assert third["group_id"] is None


@pytest.mark.unit
def test_text_cue_forces_an_unordered_group_even_when_the_model_says_strict() -> None:
    text = "1. Unplug the data cable.\n2. Unplug the power cable in either order.\n"
    steps = [
        step("Unplug the data cable.", parts=["data cable"]),
        step("Unplug the power cable in either order.", parts=["power cable"]),
    ]

    result, _ = compile_ok(steps, text=text)

    first, second = result.graph["steps"]
    assert first["group_id"] == second["group_id"] == "grp_01"


@pytest.mark.unit
def test_cache_serves_a_second_compile_without_calling_the_model() -> None:
    cache: dict[str, str] = {}
    compiler = FakeCompiler([response(DEFAULT_STEPS)])

    first = compile_sop(source(), compiler=compiler, cache=cache)
    second = compile_sop(source(), compiler=compiler, cache=cache)

    assert first.cached is False
    assert second.cached is True
    assert second.graph["steps"] == first.graph["steps"]
    assert len(compiler.prompts) == 1
    assert len(cache) == 1


@pytest.mark.unit
def test_empty_source_is_rejected_without_a_model_call() -> None:
    compiler = FakeCompiler([])

    with pytest.raises(CompileError) as caught:
        compile_sop(source("   "), compiler=compiler)

    assert caught.value.attempts == 0
    assert "empty_source" in caught.value.issues
    assert compiler.prompts == []


@pytest.mark.unit
def test_scanned_pdf_without_text_is_rejected() -> None:
    compiler = FakeCompiler([])

    with pytest.raises(CompileError) as caught:
        compile_sop(source(text="", needs_vision=True), compiler=compiler)

    assert "needs_vision" in caught.value.issues
    assert compiler.prompts == []


@pytest.mark.unit
def test_prompt_carries_the_rules_and_the_sop_text() -> None:
    prompt = prompt_for(source())

    assert PROMPT_VERSION in prompt
    assert SOP_TEXT.strip().splitlines()[0] in prompt
    assert "hand" in prompt
    assert "any order" in prompt.lower()
    assert "must" in prompt.lower()
    assert "JSON" in prompt


@pytest.mark.unit
def test_long_source_is_truncated_deterministically() -> None:
    text = "\n".join(f"{index}. Tighten bolt {index}." for index in range(1, 400))
    compiler = FakeCompiler([response(DEFAULT_STEPS)])

    compile_sop(source(text), compiler=compiler)

    assert len(compiler.prompts[0]) < 40_000
    again = FakeCompiler([response(DEFAULT_STEPS)])
    compile_sop(source(text), compiler=again)
    assert again.prompts[0] == compiler.prompts[0]


@pytest.mark.unit
def test_sop_id_comes_from_the_source_hash() -> None:
    result, _ = compile_ok()

    assert result.graph["sop_id"] == f"sop_{SHA[:8]}"
