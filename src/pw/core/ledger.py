"""Per-run cost ledger: concurrency-safe reservations, atomic JSON persistence.

The spend cap is checked *before* a call with a conservative reservation, so parallel
calls cannot jointly overshoot it. When the call settles, the reservation is released
and the measured cost is appended. `replay`/`demo` entries cost 0 USD but stay visible.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from pw.clients.errors import SpendCapExceeded
from pw.clients.pricing import usd_for

LEDGER_VERSION = 1


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    model: str
    operation: str
    mode: str = "live"
    tokens_in: int = 0
    tokens_out: int = 0
    images: int = 0
    sam_units: int = 0
    usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False
    request_hash: str = ""


class RunLedger:
    """One ledger file per run; safe to share between threads."""

    def __init__(self, path: Path, cap_usd: float = 3.0) -> None:
        if cap_usd <= 0:
            raise ValueError("cap_usd must be positive")
        self.path = path
        self.cap_usd = cap_usd
        self._lock = threading.RLock()
        self._entries: list[LedgerEntry] = []
        self._reserved_usd = 0.0
        self._load()

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    @property
    def total_usd(self) -> float:
        with self._lock:
            return round(sum(entry.usd for entry in self._entries), 8)

    @property
    def remaining_usd(self) -> float:
        with self._lock:
            return round(self.cap_usd - self.total_usd - self._reserved_usd, 8)

    @contextmanager
    def budget(self, estimated_usd: float) -> Iterator[None]:
        """Reserve an estimate, or raise `SpendCapExceeded` without calling the model."""
        with self._lock:
            spent = sum(entry.usd for entry in self._entries)
            if spent + self._reserved_usd + estimated_usd > self.cap_usd:
                raise SpendCapExceeded(round(spent, 8), estimated_usd, self.cap_usd)
            self._reserved_usd += estimated_usd
        try:
            yield
        finally:
            with self._lock:
                self._reserved_usd = max(0.0, self._reserved_usd - estimated_usd)

    def record(self, entry: LedgerEntry) -> LedgerEntry:
        priced = entry
        if not entry.cache_hit and entry.usd == 0.0:
            priced = LedgerEntry(
                **{
                    **asdict(entry),
                    "usd": usd_for(
                        entry.model,
                        tokens_in=entry.tokens_in,
                        tokens_out=entry.tokens_out,
                        images=entry.images,
                        frames=entry.sam_units,
                    ),
                }
            )
        with self._lock:
            self._entries.append(priced)
            self._write()
        return priced

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for raw in payload.get("entries", []):
            try:
                self._entries.append(LedgerEntry(**raw))
            except TypeError:
                continue

    def _write(self) -> None:
        payload = {
            "version": LEDGER_VERSION,
            "cap_usd": self.cap_usd,
            "total_usd": round(sum(entry.usd for entry in self._entries), 8),
            "entries": [asdict(entry) for entry in self._entries],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


__all__ = ["LEDGER_VERSION", "LedgerEntry", "RunLedger"]
