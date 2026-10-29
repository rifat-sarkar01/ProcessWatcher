"""Constant-time access-code verification and the FastAPI dependency."""

from __future__ import annotations

import pytest

from pw.security.access import AccessDenied, require_access_code, verify_access_code


def test_matching_code_passes() -> None:
    verify_access_code("s3cret-code", expected="s3cret-code")


def test_missing_code_is_denied() -> None:
    with pytest.raises(AccessDenied) as info:
        verify_access_code(None, expected="s3cret-code")
    assert info.value.code == "E-05"
    assert info.value.status_code == 401


def test_wrong_code_is_denied() -> None:
    with pytest.raises(AccessDenied):
        verify_access_code("wrong", expected="s3cret-code")


def test_unset_expected_code_fails_closed() -> None:
    with pytest.raises(AccessDenied):
        verify_access_code("anything", expected="")
    with pytest.raises(AccessDenied):
        verify_access_code("", expected="")


def test_unicode_codes_compare_without_type_errors() -> None:
    verify_access_code("cödé-✓", expected="cödé-✓")
    with pytest.raises(AccessDenied):
        verify_access_code("cödé", expected="cödé-✓")


def test_dependency_reads_the_env_and_denies_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PW_ACCESS_CODE", "demo-code")
    require_access_code("demo-code")
    with pytest.raises(AccessDenied):
        require_access_code("nope")
    monkeypatch.delenv("PW_ACCESS_CODE")
    with pytest.raises(AccessDenied):
        require_access_code("demo-code")
