"""Persistent outage history. No Qt imports."""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

MAX_ENTRIES = 500


@dataclass(frozen=True)
class HistoryEntry:
    disconnected_at: datetime
    reconnected_at: datetime
    duration: float  # seconds

    def to_dict(self) -> dict:
        return {
            "disconnected_at": self.disconnected_at.isoformat(),
            "reconnected_at": self.reconnected_at.isoformat(),
            "duration": round(self.duration, 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        return cls(
            datetime.fromisoformat(data["disconnected_at"]),
            datetime.fromisoformat(data["reconnected_at"]),
            float(data["duration"]),
        )


class OutageHistory:
    """Completed outages, oldest first. ``path=None`` keeps everything in memory."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._entries: list[HistoryEntry] = []
        self._lock = threading.Lock()
        self._load()

    @property
    def entries(self) -> list[HistoryEntry]:
        with self._lock:
            return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def total_downtime(self) -> float:
        return sum(e.duration for e in self.entries)

    def add(self, entry: HistoryEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            del self._entries[:-MAX_ENTRIES]
        self._save()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
        self._save()

    def _load(self) -> None:
        if not self.path:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = [HistoryEntry.from_dict(item) for item in raw][-MAX_ENTRIES:]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("Could not read history (%s); starting empty", exc)
            try:
                self.path.replace(self.path.with_suffix(".corrupt"))
            except OSError:
                pass

    def _save(self) -> None:
        if not self.path:
            return
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps([e.to_dict() for e in self.entries], indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            log.exception("Could not save history to %s", self.path)
