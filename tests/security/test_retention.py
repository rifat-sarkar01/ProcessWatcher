"""24 h retention purge with demo-case exemptions."""

from __future__ import annotations

import os
import time
from pathlib import Path

from pw.security.retention import purge_expired

DAY_S = 24 * 60 * 60


def _run(root: Path, name: str, *, age_s: float, now: float) -> Path:
    path = root / "runs" / name
    path.mkdir(parents=True)
    (path / "report.json").write_text("{}", encoding="utf-8")
    stamp = now - age_s
    os.utime(path, (stamp, stamp))
    return path


def test_old_runs_are_purged_and_fresh_runs_are_kept(scratch: Path) -> None:
    now = time.time()
    old = _run(scratch, "run_old", age_s=DAY_S + 60, now=now)
    fresh = _run(scratch, "run_fresh", age_s=DAY_S - 60, now=now)
    purged = purge_expired(scratch / "runs", now=now)
    assert purged == ["run_old"]
    assert not old.exists()
    assert fresh.exists()


def test_exempt_directories_survive(scratch: Path) -> None:
    now = time.time()
    demo = _run(scratch, "case_a", age_s=10 * DAY_S, now=now)
    old = _run(scratch, "run_old", age_s=10 * DAY_S, now=now)
    purged = purge_expired(scratch / "runs", now=now, exempt=[demo])
    assert purged == ["run_old"]
    assert demo.exists()
    assert not old.exists()


def test_missing_runs_directory_is_a_noop(scratch: Path) -> None:
    assert purge_expired(scratch / "absent") == []


def test_retention_is_exactly_24_hours_by_default(scratch: Path) -> None:
    now = time.time()
    boundary = _run(scratch, "run_boundary", age_s=DAY_S - 1, now=now)
    assert purge_expired(scratch / "runs", now=now) == []
    assert boundary.exists()
