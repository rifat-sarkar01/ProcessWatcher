"""Environment configuration: load `.env` into `os.environ`, then validate it.

`pw` and the API call `load_env_file()` once at start-up. Values already present in the
environment win, so CI and explicit exports override the file. The Meta key is only read
here and never printed: `Settings.describe()` and `repr(Settings)` redact it.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

MODES = ("live", "replay", "fake", "demo")
DEFAULT_MODE = "replay"
DEFAULT_SPEND_CAP_USD = 3.0
DEFAULT_RUNS_DIR = "runs"
ENV_FILE_VAR = "PW_ENV_FILE"
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


class ConfigError(ValueError):
    """An invalid or missing environment setting; the message is safe to display."""


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str
    meta_api_key: str
    access_code: str
    spend_cap_usd: float
    runs_dir: Path
    disable_illustrations: bool = False
    disable_verifier: bool = False

    @property
    def has_meta_key(self) -> bool:
        return bool(self.meta_api_key)

    def describe(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "meta_api_key": "set" if self.has_meta_key else "missing",
            "access_code": "set" if self.access_code else "missing",
            "spend_cap_usd": self.spend_cap_usd,
            "runs_dir": str(self.runs_dir),
            "disable_illustrations": self.disable_illustrations,
            "disable_verifier": self.disable_verifier,
        }

    def __repr__(self) -> str:
        pairs = ", ".join(f"{name}={value!r}" for name, value in self.describe().items())
        return f"Settings({pairs})"


def parse_env_file(text: str) -> dict[str, str]:
    """Parse `KEY=value` lines; comments, blanks and malformed lines are skipped."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def env_file_path(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    override = source.get(ENV_FILE_VAR, "").strip()
    return Path(override) if override else Path.cwd() / ".env"


def load_env_file(
    path: Path | None = None, *, environ: MutableMapping[str, str] | None = None
) -> Path | None:
    """Load `path` (or `$PW_ENV_FILE`, or `./.env`) without overriding set variables."""
    env = os.environ if environ is None else environ
    target = env_file_path(env) if path is None else path
    if not target.is_file():
        return None
    env.update(
        {
            key: value
            for key, value in parse_env_file(target.read_text(encoding="utf-8")).items()
            if key not in env
        }
    )
    return target


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Validate the environment and return typed settings; raises `ConfigError`."""
    source = os.environ if env is None else env
    mode = (source.get("PW_MODE") or DEFAULT_MODE).strip().lower()
    if mode not in MODES:
        raise ConfigError(f"PW_MODE must be one of {', '.join(MODES)}; got {mode!r}")
    meta_api_key = (source.get("META_API_KEY") or "").strip()
    if mode == "live" and not meta_api_key:
        raise ConfigError("PW_MODE=live needs META_API_KEY; set it in .env or the environment")
    return Settings(
        mode=mode,
        meta_api_key=meta_api_key,
        access_code=(source.get("PW_ACCESS_CODE") or "").strip(),
        spend_cap_usd=_spend_cap(source.get("PW_SPEND_CAP_USD")),
        runs_dir=Path((source.get("PW_RUNS_DIR") or DEFAULT_RUNS_DIR).strip()),
        disable_illustrations=_flag(source, "PW_DISABLE_ILLUSTRATIONS"),
        disable_verifier=_flag(source, "PW_DISABLE_VERIFIER"),
    )


def _spend_cap(raw: str | None) -> float:
    if raw is None or not raw.strip():
        return DEFAULT_SPEND_CAP_USD
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"PW_SPEND_CAP_USD must be a positive number; got {raw!r}")
    return value


def _flag(source: Mapping[str, str], name: str) -> bool:
    raw = (source.get(name) or "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(f"{name} must be a boolean (1/0, true/false, yes/no, on/off); got {raw!r}")


__all__ = [
    "DEFAULT_MODE",
    "ENV_FILE_VAR",
    "MODES",
    "ConfigError",
    "Settings",
    "env_file_path",
    "load_env_file",
    "load_settings",
    "parse_env_file",
]
