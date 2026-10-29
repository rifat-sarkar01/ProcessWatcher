"""Self-contained audit export: one HTML file with inlined images, then PDF.

The HTML has no external references (inline CSS, `data:` images, no scripts) and
carries the permanent illustration disclaimer. PDF is printed by a headless
Chromium/Edge binary; a missing browser is a typed `ExportError` (E-11: download the
HTML instead).
"""

from __future__ import annotations

import base64
import html
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pw.report.build import format_mmss

DISCLAIMER = "AI illustrations are generated reference images, not evidence."
TEMPLATE_DIR = Path(__file__).with_name("templates")
HTML_NAME = "report.html"
PDF_NAME = "report.pdf"
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")
_KNOWN_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


class ExportError(RuntimeError):
    """The export could not be produced; the HTML is the documented fallback."""


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    fmt: str
    size_bytes: int


def find_browser() -> str | None:
    """Locate a headless-capable Chromium/Edge, honouring `PW_CHROMIUM`."""
    configured = os.environ.get("PW_CHROMIUM")
    if configured and Path(configured).is_file():
        return configured
    for name in _BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    for candidate in _KNOWN_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def _safe_path(run_dir: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    root = run_dir.resolve()
    candidate = (root / relative).resolve()
    return candidate if candidate.is_relative_to(root) and candidate.is_file() else None


def _data_uri(path: Path | None) -> str | None:
    if path is None:
        return None
    mime = _MIME.get(path.suffix.lower())
    if mime is None:
        return None
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _text(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _manifest(report: Mapping[str, Any], run_dir: Path) -> Mapping[str, Any] | None:
    reference = report.get("manifest_ref")
    if not isinstance(reference, str):
        return None
    target = _safe_path(run_dir, reference)
    if target is None:
        return None
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, Mapping) else None


def _head(report: Mapping[str, Any]) -> str:
    css = (TEMPLATE_DIR / "report.css").read_text(encoding="utf-8")
    title = f"Process Watcher report {report.get('run_id', '')}".strip()
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_text(title)}</title>\n<style>\n{css}\n</style>\n</head>\n<body>"
    )


def _header(report: Mapping[str, Any]) -> str:
    video = _mapping(report.get("video"))
    return (
        f"<h1>{_text(report.get('run_id', 'run'))}</h1>"
        f'<p class="meta">status {_text(report.get("status"))} · '
        f"created {_text(report.get('created_at'))} · "
        f"video sha256 {_text(video.get('sha256'))} · "
        f"duration {_text(video.get('duration_s'))} s</p>"
        + (f'<p class="meta">{_text(report.get("notice"))}</p>' if report.get("notice") else "")
    )


def _summary(report: Mapping[str, Any]) -> str:
    summary = _mapping(report.get("summary"))
    by_type = _mapping(summary.get("by_type"))
    return (
        '<h2>Summary</h2><p class="summary">'
        f"flagged {_text(summary.get('flagged'))} · "
        f"needs review {_text(summary.get('needs_review'))} · "
        f"dropped {_text(summary.get('dropped'))} · "
        f"missed {_text(by_type.get('missed'))} · "
        f"out of order {_text(by_type.get('out_of_order'))} · "
        f"wrong tool {_text(by_type.get('wrong_tool'))}</p>"
    )


def _manifest_section(manifest: Mapping[str, Any] | None) -> str:
    if manifest is None:
        return '<h2>Manifest</h2><p class="missing">Manifest unavailable</p>'
    models = manifest.get("models")
    names = (
        ", ".join(_text(model.get("name")) for model in models if isinstance(model, Mapping))
        if isinstance(models, list)
        else ""
    )
    ledger = _mapping(manifest.get("ledger"))
    return (
        "<h2>Manifest</h2><table>"
        f"<tr><th>mode</th><td>{_text(manifest.get('mode'))}</td></tr>"
        f"<tr><th>models</th><td>{names or 'unknown'}</td></tr>"
        f"<tr><th>total_usd</th><td>{_text(ledger.get('total_usd'))}</td></tr>"
        f"<tr><th>config_sha256</th><td>{_text(manifest.get('config_sha256'))}</td></tr>"
        "</table>"
    )


def _evidence_block(deviation: Mapping[str, Any], run_dir: Path) -> str:
    items = deviation.get("evidence")
    figures: list[str] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            uri = _data_uri(_safe_path(run_dir, item.get("output_path")))
            caption = (
                f"{_text(item.get('evidence_id'))} · frame {_text(item.get('frame_index'))} · "
                f"t {_text(item.get('t'))} s · sha256 {_text(item.get('output_sha256'))}"
            )
            image = (
                f'<img src="{uri}" alt="evidence frame">'
                if uri
                else ('<p class="missing">Evidence unavailable</p>')
            )
            figures.append(f"<figure>{image}<figcaption>{caption}</figcaption></figure>")
    if not figures:
        figures.append('<p class="missing">Evidence unavailable</p>')
    return '<div class="evidence">' + "".join(figures) + "</div>"


def _illustration_block(deviation: Mapping[str, Any], run_dir: Path) -> str:
    illustration = deviation.get("illustration")
    if not isinstance(illustration, Mapping):
        reason = deviation.get("illustration_unavailable_reason")
        label = reason if isinstance(reason, str) and reason else "Illustration unavailable"
        return f'<div class="illustration"><p class="missing">{_text(label)}</p></div>'
    uri = _data_uri(_safe_path(run_dir, illustration.get("path")))
    image = (
        f'<img src="{uri}" alt="AI illustration, not evidence">'
        if uri
        else '<p class="missing">Illustration unavailable</p>'
    )
    return (
        f'<div class="illustration">{image}'
        '<p class="watermark">AI illustration — not evidence</p></div>'
    )


def _deviation_card(deviation: Mapping[str, Any], run_dir: Path) -> str:
    status = str(deviation.get("status") or "")
    severity = str(deviation.get("severity") or "")
    tools_expected = ", ".join(str(item) for item in deviation.get("expected_tools") or [])
    tools_observed = ", ".join(str(item) for item in deviation.get("observed_tools") or [])
    tracks = ", ".join(str(item) for item in deviation.get("track_ids") or [])
    return (
        f'<section class="deviation" id="{_text(deviation.get("id"))}">'
        f"<h3>{_text(deviation.get('id'))} · {_text(deviation.get('type'))} · "
        f"step {_text(deviation.get('step_id'))}</h3>"
        f'<p><span class="badge {html.escape(status)}">{_text(status)}</span> '
        f'<span class="badge {html.escape(severity)}">{_text(severity)}</span></p>'
        f'<p class="explanation">{_text(deviation.get("explanation"))}</p>'
        '<dl class="facts">'
        f"<dt>time</dt><dd>{format_mmss(float(deviation.get('t_start') or 0))} &ndash; "
        f"{format_mmss(float(deviation.get('t_end') or 0))}</dd>"
        f"<dt>confidence</dt><dd>{_text(deviation.get('confidence'))}</dd>"
        f"<dt>margin</dt><dd>{_text(deviation.get('margin'))}</dd>"
        f"<dt>tracks</dt><dd>{_text(tracks)}</dd>"
        + (f"<dt>expected tools</dt><dd>{_text(tools_expected)}</dd>" if tools_expected else "")
        + (f"<dt>observed tools</dt><dd>{_text(tools_observed)}</dd>" if tools_observed else "")
        + "</dl>"
        + _evidence_block(deviation, run_dir)
        + _illustration_block(deviation, run_dir)
        + "</section>"
    )


def render_html(report: Mapping[str, Any], run_dir: Path) -> str:
    """Render the full self-contained report as a single HTML string."""
    source = Path(run_dir)
    manifest = _manifest(report, source)
    deviations = report.get("deviations")
    cards = (
        "".join(
            _deviation_card(deviation, source)
            for deviation in deviations
            if isinstance(deviation, Mapping)
        )
        if isinstance(deviations, list)
        else ""
    )
    return "\n".join(
        (
            _head(report),
            _header(report),
            _summary(report),
            _manifest_section(manifest),
            "<h2>Deviations</h2>",
            cards or '<p class="missing">No deviations were reported.</p>',
            f'<p class="disclaimer">{DISCLAIMER} Evidence items are real SAM-annotated '
            "frames; illustrations are watermarked and never appear in evidence.</p>",
            "</body>\n</html>\n",
        )
    )


def _print_pdf(browser: str, html_path: Path, pdf_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="pw-pdf-") as profile:
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=120, shell=False, check=False
        )
    if completed.returncode != 0 or not pdf_path.is_file():
        detail = completed.stderr.strip().splitlines()
        reason = detail[-1] if detail else f"exit code {completed.returncode}"
        raise ExportError(f"headless print failed: {reason}")


def write_export(
    report: Mapping[str, Any],
    run_dir: Path,
    *,
    fmt: str = "html",
    out_dir: Path | None = None,
) -> ExportResult:
    """Write `report.html` (and `report.pdf` when asked) and return its size."""
    if fmt not in {"html", "pdf"}:
        raise ValueError(f"unknown export format: {fmt}")
    source = Path(run_dir)
    target_dir = Path(out_dir) if out_dir is not None else source
    target_dir.mkdir(parents=True, exist_ok=True)
    html_path = target_dir / HTML_NAME
    html_path.write_text(render_html(report, source), encoding="utf-8")
    if fmt == "html":
        return ExportResult(html_path, "html", html_path.stat().st_size)

    browser = find_browser()
    if browser is None:
        raise ExportError("no headless Chromium/Edge found; download the HTML instead")
    pdf_path = target_dir / PDF_NAME
    _print_pdf(browser, html_path, pdf_path)
    return ExportResult(pdf_path, "pdf", pdf_path.stat().st_size)


__all__ = [
    "DISCLAIMER",
    "HTML_NAME",
    "PDF_NAME",
    "ExportError",
    "ExportResult",
    "find_browser",
    "render_html",
    "write_export",
]
