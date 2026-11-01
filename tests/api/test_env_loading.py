"""The API app loads `.env` at startup and rejects an unusable live configuration."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pw.api.main import create_app
from pw.core.settings import ConfigError
from pw.security.access import AccessDenied, verify_access_code

CODE = "env-file-access-code"


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in ("PW_MODE", "META_API_KEY", "PW_ACCESS_CODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PW_ENV_FILE", str(tmp_path / "absent.env"))
    yield


def test_create_app_loads_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs_dir: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"PW_ACCESS_CODE={CODE}\n", encoding="utf-8")
    monkeypatch.setenv("PW_ENV_FILE", str(env_file))
    create_app(runs_dir=runs_dir)
    verify_access_code(CODE)


def test_create_app_rejects_live_without_a_key(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PW_MODE", "live")
    with pytest.raises(ConfigError, match="META_API_KEY"):
        create_app(runs_dir=runs_dir)


def test_create_app_rejects_an_unknown_mode(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PW_MODE", "staging")
    with pytest.raises(ConfigError, match="PW_MODE"):
        create_app(runs_dir=runs_dir)


def test_access_code_from_env_file_is_not_required_for_public_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs_dir: Path
) -> None:
    from fastapi.testclient import TestClient

    env_file = tmp_path / ".env"
    env_file.write_text(f"PW_ACCESS_CODE={CODE}\n", encoding="utf-8")
    monkeypatch.setenv("PW_ENV_FILE", str(env_file))
    client = TestClient(create_app(runs_dir=runs_dir))
    assert client.get("/healthz").status_code == 200
    with pytest.raises(AccessDenied):
        verify_access_code("wrong")
