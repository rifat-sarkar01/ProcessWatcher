"""`pw config` diagnostics and mode resolution in the `pw run` entry point."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import pw.cli as cli

SECRET = "local-test-key-0000000000000000000000000001"
MANAGED = (
    "PW_MODE",
    "META_API_KEY",
    "PW_SPEND_CAP_USD",
    "PW_RUNS_DIR",
    "PW_DISABLE_ILLUSTRATIONS",
    "PW_DISABLE_VERIFIER",
)


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in (*MANAGED, "PW_ENV_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PW_ENV_FILE", str(tmp_path / "absent.env"))
    yield


def test_config_prints_redacted_settings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PW_MODE", "live")
    monkeypatch.setenv("META_API_KEY", SECRET)
    assert cli.main(["config"]) == 0
    output = capsys.readouterr().out
    assert SECRET not in output
    payload = json.loads(output)
    assert payload["mode"] == "live"
    assert payload["meta_api_key"] == "set"


def test_config_loads_the_env_file_named_by_pw_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text(f"PW_MODE=fake\nMETA_API_KEY={SECRET}\n", encoding="utf-8")
    monkeypatch.setenv("PW_ENV_FILE", str(env_file))
    assert cli.main(["config"]) == 0
    output = capsys.readouterr().out
    assert SECRET not in output
    assert json.loads(output)["mode"] == "fake"


def test_run_uses_pw_mode_when_the_flag_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run_pipeline(**kwargs: object) -> object:
        captured.append(str(kwargs["mode"]))
        raise cli.PipelineError("stop here", exit_code=0)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)
    monkeypatch.setenv("PW_MODE", "fake")
    assert cli.main(["run", "--video", "a.mp4", "--sop", "b.md"]) == 0
    assert captured == ["fake"]


def test_run_flag_overrides_pw_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def fake_run_pipeline(**kwargs: object) -> object:
        captured.append(str(kwargs["mode"]))
        raise cli.PipelineError("stop here", exit_code=0)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)
    monkeypatch.setenv("PW_MODE", "replay")
    assert cli.main(["run", "--mode", "fake", "--video", "a.mp4", "--sop", "b.md"]) == 0
    assert captured == ["fake"]


def test_run_rejects_an_unknown_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PW_MODE", "staging")
    assert cli.main(["run", "--video", "a.mp4", "--sop", "b.md"]) == 2
    assert "PW_MODE" in capsys.readouterr().err


def test_run_reports_a_missing_key_for_live(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PW_MODE", "live")
    assert cli.main(["run", "--video", "a.mp4", "--sop", "b.md"]) == 2
    assert "META_API_KEY" in capsys.readouterr().err
