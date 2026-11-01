"""Manual smoke test: one cheap call per model through the real client layer.

    uv run python -m pw.clients.selftest --mode live --models all

`replay` serves the previous run's cache without spending. This is the AGENTS.md
"live selftest OK for all 3 models" gate; it is never run by CI.
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

from pw.clients import build_clients
from pw.core.ledger import RunLedger
from pw.core.settings import load_env_file, load_settings

MODELS = ("wonder", "image", "sam")

OK_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def _wonder_payload() -> dict[str, object]:
    return {
        "model": "muse-wonder-1.0",
        "temperature": 0,
        "reasoning": {"effort": "low"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "selftest",
                "schema": OK_SCHEMA,
                "strict": True,
            }
        },
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": 'Return JSON {"ok": true}.'}],
            }
        ],
    }


def _sam_payload() -> dict[str, object]:
    image = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(image).rectangle((16, 16, 48, 48), fill="red")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "model": "sam-3.1",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "red square"},
                    {"type": "input_image", "image_url": url},
                ],
            }
        ],
        "metadata": {"mask_encoding": "one_bit"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pw.clients.selftest")
    parser.add_argument("--mode", choices=("live", "replay"), default=None)
    parser.add_argument(
        "--models", default="all", help="all or a comma list of " + ", ".join(MODELS)
    )
    parser.add_argument("--ledger", type=Path, default=None)
    args = parser.parse_args(argv)

    load_env_file()
    settings = load_settings()
    mode = args.mode or settings.mode
    if mode not in ("live", "replay"):
        print(f"selftest: mode must be live or replay, got {mode!r}", file=sys.stderr)
        return 2
    if mode == "live" and not settings.has_meta_key:
        print("selftest: META_API_KEY is not set", file=sys.stderr)
        return 2
    requested = (
        MODELS if args.models == "all" else tuple(part.strip() for part in args.models.split(","))
    )
    unknown = [name for name in requested if name not in MODELS]
    if unknown:
        print(f"selftest: unknown model(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    ledger_path = args.ledger or Path(tempfile.gettempdir()) / "pw-selftest" / "ledger.json"
    ledger = RunLedger(ledger_path, cap_usd=settings.spend_cap_usd)
    clients = build_clients(mode=mode, ledger=ledger, api_key=settings.meta_api_key)
    failures = 0
    try:
        if "wonder" in requested:
            failures += _check(
                "wonder", lambda: _wonder(clients.wonder.create_response(_wonder_payload()))
            )
        if "image" in requested:
            failures += _check(
                "image",
                lambda: _image(
                    clients.image.generate("A single blue square on a white background.")
                ),
            )
        if "sam" in requested:
            failures += _check("sam", lambda: _sam(clients.sam.segment(_sam_payload())))
    finally:
        clients.close()

    print(
        f"selftest: {len(requested) - failures}/{len(requested)} OK - spent ${ledger.total_usd:.4f}"
    )
    return 0 if failures == 0 else 1


def _check(name: str, call: Callable[[], str]) -> int:
    try:
        detail = call()
    except Exception as error:
        print(f"{name}: FAIL {type(error).__name__}: {error}")
        return 1
    print(f"{name}: OK {detail}")
    return 0


def _wonder(result: object) -> str:
    text = getattr(result, "text", None)
    return (
        f"text={text!r} tokens={getattr(result, 'tokens_in', 0)}/{getattr(result, 'tokens_out', 0)}"
    )


def _image(result: object) -> str:
    images = getattr(result, "images", ())
    return f"{len(images)} image(s), {sum(len(item) for item in images)} bytes"


def _sam(result: object) -> str:
    units = getattr(result, "sam_units", 0)
    return f"sam_units={units}"


if __name__ == "__main__":
    raise SystemExit(main())
