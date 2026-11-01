"""`.env` parsing, loading and validation of the run-mode settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from pw.core.settings import (
    ConfigError,
    load_env_file,
    load_settings,
    parse_env_file,
)

SECRET = "local-test-key-0000000000000000000000000001"


def test_parse_env_file_reads_pairs_and_skips_comments_and_blanks() -> None:
    values = parse_env_file("# comment\n\nPW_MODE=replay\nPW_RUNS_DIR=runs\n")
    assert values == {"PW_MODE": "replay", "PW_RUNS_DIR": "runs"}


def test_parse_env_file_strips_quotes_export_and_inline_comments() -> None:
    text = f'export META_API_KEY="{SECRET}"\nPW_RUNS_DIR=runs  # where runs land\n'
    values = parse_env_file(text)
    assert values["META_API_KEY"] == SECRET
    assert values["PW_RUNS_DIR"] == "runs"


def test_parse_env_file_keeps_empty_values() -> None:
    assert parse_env_file("PW_ACCESS_CODE=\n") == {"PW_ACCESS_CODE": ""}


def test_parse_env_file_ignores_lines_without_a_key() -> None:
    assert parse_env_file("just-prose\n=value\n") == {}


def test_load_env_file_fills_missing_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"META_API_KEY={SECRET}\n", encoding="utf-8")
    environ: dict[str, str] = {}
    assert load_env_file(env_file, environ=environ) == env_file
    assert environ == {"META_API_KEY": SECRET}


def test_load_env_file_never_overrides_an_existing_variable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("META_API_KEY=from-file\n", encoding="utf-8")
    environ = {"META_API_KEY": "from-shell"}
    load_env_file(env_file, environ=environ)
    assert environ["META_API_KEY"] == "from-shell"


def test_load_env_file_returns_none_when_absent(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "missing.env", environ={}) is None


def test_defaults_without_any_configuration() -> None:
    settings = load_settings(env={})
    assert settings.mode == "replay"
    assert settings.spend_cap_usd == 3.0
    assert settings.runs_dir == Path("runs")
    assert settings.has_meta_key is False
    assert settings.disable_illustrations is False
    assert settings.disable_verifier is False


def test_live_without_key_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="META_API_KEY"):
        load_settings(env={"PW_MODE": "live"})


def test_live_with_key_is_valid() -> None:
    settings = load_settings(env={"PW_MODE": "live", "META_API_KEY": SECRET})
    assert settings.mode == "live"
    assert settings.has_meta_key is True


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ConfigError, match="PW_MODE"):
        load_settings(env={"PW_MODE": "production"})


def test_mode_is_case_insensitive_and_trimmed() -> None:
    assert load_settings(env={"PW_MODE": " LIVE ", "META_API_KEY": SECRET}).mode == "live"


@pytest.mark.parametrize("value", ["abc", "0", "-1", "nan", "inf"])
def test_invalid_spend_cap_is_rejected(value: str) -> None:
    with pytest.raises(ConfigError, match="PW_SPEND_CAP_USD"):
        load_settings(env={"PW_SPEND_CAP_USD": value})


def test_spend_cap_and_runs_dir_are_read() -> None:
    settings = load_settings(env={"PW_SPEND_CAP_USD": "1.5", "PW_RUNS_DIR": "tmp/runs"})
    assert settings.spend_cap_usd == 1.5
    assert settings.runs_dir == Path("tmp/runs")


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_boolean_switches_are_read(value: str) -> None:
    settings = load_settings(env={"PW_DISABLE_ILLUSTRATIONS": value, "PW_DISABLE_VERIFIER": value})
    assert settings.disable_illustrations is True
    assert settings.disable_verifier is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_boolean_switches_accept_falsey_values(value: str) -> None:
    settings = load_settings(env={"PW_DISABLE_ILLUSTRATIONS": value, "PW_DISABLE_VERIFIER": value})
    assert settings.disable_illustrations is False
    assert settings.disable_verifier is False


def test_invalid_boolean_is_rejected() -> None:
    with pytest.raises(ConfigError, match="PW_DISABLE_VERIFIER"):
        load_settings(env={"PW_DISABLE_VERIFIER": "maybe"})


def test_describe_and_repr_redact_the_key() -> None:
    settings = load_settings(env={"PW_MODE": "live", "META_API_KEY": SECRET})
    described = settings.describe()
    assert described["meta_api_key"] == "set"
    assert described["mode"] == "live"
    assert SECRET not in repr(settings)
    assert SECRET not in repr(described)
