"""Dry-run the README's fenced shell commands (T-7.3).

Every command line in a ```bash fence is parsed with `shlex`; project commands
(`uv run pw*`, `npm --prefix web run *`) are then exercised with `--help` or looked up
in `package.json`, so a renamed entry point or npm script fails the check instead of
shipping a broken quickstart. Lines with shell variables or placeholders are syntax
checked only.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
_ENTRY_POINTS = {"pw", "pw-data", "pw-bench"}


def fenced_commands(text: str) -> list[str]:
    commands: list[str] = []
    in_fence = False
    pending = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            in_fence = not in_fence and line.strip("`").strip() in {"bash", "sh", "shell"}
            pending = ""
            continue
        if not in_fence or not line.strip() or line.lstrip().startswith("#"):
            continue
        pending = f"{pending} {line.strip()}".strip() if pending else line.strip()
        if pending.endswith("\\"):
            pending = pending[:-1].strip()
            continue
        commands.append(pending)
        pending = ""
    return commands


def _has_placeholder(command: str) -> bool:
    return any(token in command for token in ("<", ">", "$", "..."))


def _check_uv(tokens: list[str]) -> str | None:
    if len(tokens) < 3 or tokens[0] != "uv" or tokens[1] != "run":
        return None
    tool = tokens[2]
    if tool not in _ENTRY_POINTS:
        return None
    script = Path(sys.executable).parent / (f"{tool}.exe" if sys.platform == "win32" else tool)
    if not script.is_file():
        return f"console script missing: {tool}"
    completed = subprocess.run(
        [str(script), "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        return f"{tool} --help failed: {completed.stderr.strip()[:200]}"
    return None


def _check_npm(tokens: list[str]) -> str | None:
    if len(tokens) < 5 or tokens[0] != "npm":
        return None
    if "--prefix" not in tokens or "run" not in tokens:
        return None
    script = tokens[tokens.index("run") + 1] if tokens.index("run") + 1 < len(tokens) else ""
    package = json.loads((REPO / "web" / "package.json").read_text(encoding="utf-8"))
    if script not in package.get("scripts", {}):
        return f"npm script missing: {script}"
    return None


def check(path: Path = README) -> tuple[int, list[str]]:
    commands = fenced_commands(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    checked = 0
    for command in commands:
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            errors.append(f"unparsable command ({exc}): {command}")
            continue
        if not tokens:
            continue
        checked += 1
        if _has_placeholder(command):
            continue
        try:
            problem = _check_uv(tokens) or _check_npm(tokens)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            problem = str(exc)
        if problem:
            errors.append(f"{command}: {problem}")
    return checked, errors


def main() -> int:
    checked, errors = check()
    for error in errors:
        print(f"README: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"{checked} commands OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
