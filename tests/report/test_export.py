"""Self-contained HTML/PDF export: deviations, inlined assets, disclaimer, size."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

from pw.cli import main as cli_main
from pw.report.export import (
    DISCLAIMER,
    ExportError,
    find_browser,
    render_html,
    write_export,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "contracts" / "examples"
SCRATCH_ROOT = ROOT / ".uv" / "tests-tmp"
FIFTEEN_MB = 15 * 1024 * 1024


@pytest.fixture
def run_dir() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"export-{uuid.uuid4().hex}"
    (path / "evidence").mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def report(run_dir: Path) -> dict[str, object]:
    payload = json.loads((EXAMPLES / "report.p-a.example.json").read_text("utf-8"))
    (run_dir / "manifest.json").write_text(
        (EXAMPLES / "manifest.example.json").read_text("utf-8"), encoding="utf-8"
    )
    Image.new("RGB", (40, 30), (12, 34, 56)).save(run_dir / "evidence" / "evd_001.png")
    Image.new("RGB", (40, 30), (65, 43, 21)).save(run_dir / "evidence" / "evd_002.png")
    (run_dir / "illustrations").mkdir()
    Image.new("RGB", (40, 30), (90, 90, 90)).save(run_dir / "illustrations" / "ill_001.png")
    return payload


def test_every_deviation_id_appears(report: dict[str, object], run_dir: Path) -> None:
    rendered = render_html(report, run_dir)
    for deviation in report["deviations"]:  # type: ignore[union-attr]
        assert deviation["id"] in rendered


def test_export_is_self_contained(report: dict[str, object], run_dir: Path) -> None:
    rendered = render_html(report, run_dir)
    assert 'src="http' not in rendered
    assert 'href="http' not in rendered
    assert "<script" not in rendered
    assert "data:image/png;base64," in rendered


def test_evidence_hashes_and_manifest_facts_are_shown(
    report: dict[str, object], run_dir: Path
) -> None:
    rendered = render_html(report, run_dir)
    evidence = report["deviations"][0]["evidence"][0]  # type: ignore[index]
    assert evidence["output_sha256"] in rendered
    assert "sam-3.1" in rendered
    assert "config_sha256" in rendered or "5e7d9b1a2c4" in rendered


def test_illustration_carries_the_permanent_disclaimer(
    report: dict[str, object], run_dir: Path
) -> None:
    rendered = render_html(report, run_dir)
    assert DISCLAIMER in rendered
    assert "ai illustration — not evidence" in rendered.lower()
    assert "illustrations/ill_001.png" not in rendered


def test_missing_manifest_and_images_are_tolerated(
    report: dict[str, object], run_dir: Path
) -> None:
    (run_dir / "manifest.json").unlink()
    (run_dir / "evidence" / "evd_001.png").unlink()
    rendered = render_html(report, run_dir)
    assert "dev_001" in rendered
    assert "Evidence unavailable" in rendered
    assert "Manifest unavailable" in rendered


def test_evidence_paths_cannot_escape_the_run(report: dict[str, object], run_dir: Path) -> None:
    secret = run_dir.parent / f"secret-{uuid.uuid4().hex}.png"
    Image.new("RGB", (10, 10)).save(secret)
    report["deviations"][0]["evidence"][0]["output_path"] = "../" + secret.name  # type: ignore[index]
    rendered = render_html(report, run_dir)
    leaked = base64.b64encode(secret.read_bytes()).decode("ascii")
    assert leaked not in rendered


def test_html_export_stays_under_fifteen_megabytes(
    report: dict[str, object], run_dir: Path
) -> None:
    result = write_export(report, run_dir, fmt="html")
    assert result.path.name == "report.html"
    assert result.size_bytes < FIFTEEN_MB
    assert result.path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_unknown_format_is_rejected(report: dict[str, object], run_dir: Path) -> None:
    with pytest.raises(ValueError):
        write_export(report, run_dir, fmt="docx")


def test_cli_exports_html(report: dict[str, object], run_dir: Path) -> None:
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    out = run_dir / "export"
    assert cli_main(["export", str(run_dir), "--format", "html", "--out", str(out)]) == 0
    rendered = (out / "report.html").read_text(encoding="utf-8")
    assert "dev_001" in rendered


def test_cli_reports_missing_report(run_dir: Path) -> None:
    assert cli_main(["export", str(run_dir), "--format", "html"]) == 2


def test_pdf_export_when_a_browser_is_available(report: dict[str, object], run_dir: Path) -> None:
    browser = find_browser()
    if browser is None:
        pytest.skip("no headless Chromium/Edge on this host")
    result = write_export(report, run_dir, fmt="pdf")
    data = result.path.read_bytes()
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page") >= 1


def test_pdf_without_a_browser_raises_a_typed_error(
    report: dict[str, object], run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PW_CHROMIUM", "")
    monkeypatch.setattr("pw.report.export.find_browser", lambda: None)
    with pytest.raises(ExportError):
        write_export(report, run_dir, fmt="pdf")


def test_pdf_subprocess_failure_is_typed(
    report: dict[str, object], run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pw.report.export.find_browser", lambda: "/bin/false")

    def fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("pw.report.export.subprocess.run", fail)
    with pytest.raises(ExportError):
        write_export(report, run_dir, fmt="pdf")
