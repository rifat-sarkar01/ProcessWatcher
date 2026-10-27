"""Smoke test: the package imports and exposes a version."""

import pw


def test_import_pw() -> None:
    assert pw.__name__ == "pw"
    assert isinstance(pw.__version__, str)
    assert pw.__version__
