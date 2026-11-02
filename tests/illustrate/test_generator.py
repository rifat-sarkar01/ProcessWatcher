"""T-4.3: illustration prompts, dedupe, reference edits, cache and failure fallback."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from pw.align.deviations import Deviation
from pw.illustrate.generator import (
    UNAVAILABLE,
    client_caller,
    generate_illustrations,
    illustrations_disabled,
)
from pw.illustrate.prompts import PROMPT_VERSION, build_prompt, caption_for

SOP = {
    "schema_version": "1.0.0",
    "sop_id": "sop_00000000",
    "title": "Test",
    "source": {"kind": "md", "sha256": "a" * 64},
    "steps": [
        {
            "id": "stp_01",
            "idx": 1,
            "text": "Unplug the power cable from the rear of the case.",
            "action": "unplug the power cable",
            "tools": ["hand"],
            "parts": ["power cable"],
            "ordering": "strict",
            "group_id": None,
            "critical": True,
            "visual_check": None,
        },
        {
            "id": "stp_02",
            "idx": 2,
            "text": "Remove the two rear thumbscrews.",
            "action": "remove thumbscrews",
            "tools": ["screwdriver"],
            "parts": ["thumbscrews"],
            "ordering": "strict",
            "group_id": None,
            "critical": False,
            "visual_check": None,
        },
    ],
    "vocabulary": {"sam_concepts": ["hand"]},
    "warnings": [],
}


def _deviation(
    identifier: str = "dev_001", step_id: str = "stp_01", kind: str = "missed"
) -> Deviation:
    return Deviation(
        id=identifier,
        type=kind,
        status="flagged",
        severity="high",
        step_id=step_id,
        t_start=1.0,
        t_end=2.0,
        track_ids=("trk_001",),
        confidence=0.9,
        margin=0.5,
    )


def _png(color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buffer, format="PNG")
    return buffer.getvalue()


class Caller:
    def __init__(self, output: bytes | None = None, error: Exception | None = None) -> None:
        self.output = _png() if output is None else output
        self.error = error
        self.prompts: list[str] = []
        self.references: list[bytes | None] = []

    def __call__(self, prompt: str, reference: bytes | None) -> bytes:
        self.prompts.append(prompt)
        self.references.append(reference)
        if self.error is not None:
            raise self.error
        return self.output


@pytest.mark.unit
def test_caption_is_short_uppercase_and_deterministic() -> None:
    caption = caption_for(SOP["steps"][0])

    assert caption == "UNPLUG POWER CABLE"
    assert len(caption.split()) <= 3
    assert caption == caption_for(SOP["steps"][0])


@pytest.mark.unit
def test_prompt_carries_style_tools_and_caption() -> None:
    prompt = build_prompt(SOP["steps"][1], deviation_types=("missed",))

    assert PROMPT_VERSION
    assert "Remove the two rear thumbscrews." in prompt
    assert "screwdriver" in prompt
    assert "thumbscrews" in prompt
    assert '"REMOVE THUMBSCREWS"' in prompt
    assert "No faces or people" in prompt


@pytest.mark.unit
def test_deviations_for_the_same_step_share_one_illustration() -> None:
    caller = Caller()
    deviations = [_deviation("dev_001"), _deviation("dev_002", kind="out_of_order")]

    result = generate_illustrations(deviations, SOP, call=caller)

    assert len(result.items) == 1
    assert result.items[0].deviation_ids == ("dev_001", "dev_002")
    assert result.items[0].id == "ill_001"
    assert result.calls == 1


@pytest.mark.unit
def test_reference_frame_selects_edit_mode() -> None:
    caller = Caller()
    reference = _png((1, 2, 3))

    result = generate_illustrations(
        [_deviation()], SOP, call=caller, references={"dev_001": reference}
    )

    assert result.items[0].mode == "edit"
    assert caller.references == [reference]


@pytest.mark.unit
def test_without_a_reference_it_generates_text_only() -> None:
    caller = Caller()

    result = generate_illustrations([_deviation()], SOP, call=caller)

    assert result.items[0].mode == "generate"
    assert caller.references == [None]


@pytest.mark.unit
def test_second_call_is_served_from_the_cache() -> None:
    cache: dict[str, bytes] = {}
    caller = Caller()

    first = generate_illustrations([_deviation()], SOP, call=caller, cache=cache)
    second = generate_illustrations([_deviation()], SOP, call=caller, cache=cache)

    assert first.calls == 1
    assert first.cache_hits == 0
    assert second.calls == 0
    assert second.cache_hits == 1
    assert second.items[0].from_cache is True
    assert len(caller.prompts) == 1
    assert first.items[0].image == second.items[0].image


@pytest.mark.unit
def test_cache_key_changes_with_the_reference() -> None:
    caller = Caller()
    cache: dict[str, bytes] = {}

    generate_illustrations(
        [_deviation()], SOP, call=caller, cache=cache, references={"dev_001": _png((1, 1, 1))}
    )
    generate_illustrations(
        [_deviation()], SOP, call=caller, cache=cache, references={"dev_001": _png((2, 2, 2))}
    )

    assert caller.prompts[0] == caller.prompts[1]
    assert len(cache) == 2
    assert len(caller.references) == 2


@pytest.mark.unit
def test_cache_dir_persists_images(scratch: Path) -> None:
    caller = Caller()

    first = generate_illustrations([_deviation()], SOP, call=caller, cache_dir=scratch)
    second = generate_illustrations([_deviation()], SOP, call=caller, cache_dir=scratch)

    assert first.calls == 1
    assert second.calls == 0
    assert len(list(scratch.glob("*.png"))) == 1


@pytest.mark.unit
def test_disabled_switch_makes_no_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = Caller()
    monkeypatch.setenv("PW_DISABLE_ILLUSTRATIONS", "1")

    assert illustrations_disabled() is True
    result = generate_illustrations([_deviation()], SOP, call=caller)

    assert result.disabled is True
    assert result.items == ()
    assert caller.prompts == []


@pytest.mark.unit
def test_disabled_argument_overrides_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PW_DISABLE_ILLUSTRATIONS", "1")
    caller = Caller()

    result = generate_illustrations([_deviation()], SOP, call=caller, disabled=False)

    assert result.disabled is False
    assert result.available == 1


@pytest.mark.unit
def test_api_failure_becomes_illustration_unavailable() -> None:
    caller = Caller(error=RuntimeError("upstream 500"))

    result = generate_illustrations([_deviation()], SOP, call=caller)

    item = result.items[0]
    assert item.image is None
    assert item.reason is not None
    assert item.reason.startswith(UNAVAILABLE)
    assert "RuntimeError" in item.reason


@pytest.mark.unit
def test_empty_image_becomes_illustration_unavailable() -> None:
    result = generate_illustrations([_deviation()], SOP, call=Caller(output=b""))

    assert result.items[0].image is None
    assert result.items[0].reason is not None
    assert result.items[0].reason.startswith(UNAVAILABLE)


@pytest.mark.unit
def test_max_items_limits_the_per_step_work() -> None:
    caller = Caller()
    deviations = [_deviation("dev_001", "stp_01"), _deviation("dev_002", "stp_02")]

    result = generate_illustrations(deviations, SOP, call=caller, max_items=1)

    assert len(result.items) == 1
    assert result.calls == 1


@pytest.mark.unit
def test_unknown_step_is_skipped() -> None:
    result = generate_illustrations([_deviation(step_id="stp_09")], SOP, call=Caller())

    assert result.items == ()


@pytest.mark.unit
def test_write_burns_the_watermark_and_describes_the_file(scratch: Path) -> None:
    caller = Caller()

    result = generate_illustrations([_deviation()], SOP, call=caller)
    written = result.write(scratch)

    assert len(written) == 1
    item = written[0]
    assert item["kind"] == "illustration"
    assert item["watermark"] is True
    assert item["id"] == "ill_001"
    assert item["sha256"] == hashlib.sha256((scratch / item["path"]).read_bytes()).hexdigest()
    assert item["prompt_version"] == PROMPT_VERSION
    stored = Image.open(scratch / item["path"]).convert("L")
    width, height = stored.size
    band = list(stored.tobytes())[(height - 6) * width :]
    assert sum(1 for value in band if value < 64) / len(band) > 0.5


@pytest.mark.unit
def test_write_skips_unavailable_items(scratch: Path) -> None:
    result = generate_illustrations([_deviation()], SOP, call=Caller(error=RuntimeError("x")))

    assert result.write(scratch) == ()
    assert not (scratch / "illustrations").exists()


@pytest.mark.unit
def test_client_caller_uses_edit_only_when_a_reference_exists() -> None:
    calls: list[tuple[str, object]] = []

    class FakeImageClient:
        def edit(self, prompt: str, images: list[object]) -> SimpleNamespace:
            calls.append(("edit", images))
            return SimpleNamespace(images=(b"edited",))

        def generate(self, prompt: str) -> SimpleNamespace:
            calls.append(("generate", prompt))
            return SimpleNamespace(images=(b"generated",))

    caller = client_caller(FakeImageClient())  # type: ignore[arg-type]

    assert caller("p", b"ref") == b"edited"
    assert caller("p", None) == b"generated"
    assert calls[0][0] == "edit"
    assert calls[1][0] == "generate"


@pytest.fixture
def scratch() -> Path:
    import shutil
    import uuid

    root = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp" / f"ill-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
