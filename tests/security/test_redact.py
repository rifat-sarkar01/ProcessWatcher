"""Secret redaction for logs and error payloads."""

from __future__ import annotations

from pw.security.redact import redact, redact_mapping

SECRET = "sk-live-should-never-appear"


def test_authorization_headers_are_redacted() -> None:
    text = f"POST /runs\nAuthorization: Bearer {SECRET}\nstatus=202"
    cleaned = redact(text)
    assert SECRET not in cleaned
    assert "[REDACTED]" in cleaned
    assert "status=202" in cleaned


def test_json_style_secrets_are_redacted() -> None:
    text = f'{{"X-Access-Code": "{SECRET}", "META_API_KEY": "{SECRET}"}}'
    cleaned = redact(text)
    assert SECRET not in cleaned


def test_env_assignments_are_redacted() -> None:
    text = f"META_API_KEY={SECRET}\nPW_ACCESS_CODE={SECRET}"
    assert SECRET not in redact(text)


def test_mapping_redaction_keeps_shape() -> None:
    payload = {"run_id": "run_x", "headers": {"Authorization": SECRET, "X-Access-Code": SECRET}}
    cleaned = redact_mapping(payload)
    assert cleaned["run_id"] == "run_x"
    assert cleaned["headers"]["Authorization"] == "[REDACTED]"
    assert cleaned["headers"]["X-Access-Code"] == "[REDACTED]"


def test_plain_text_is_unchanged() -> None:
    assert redact("stage=align status=done cost=0.0") == "stage=align status=done cost=0.0"
