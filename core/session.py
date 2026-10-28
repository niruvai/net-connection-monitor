"""Live statistics derived from state transitions. No Qt, no threads, injectable clock."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from core.history import HistoryEntry, OutageHistory
from core.models import ConnectionState


class SessionTracker:
    """Tracks the current outage / uptime and exposes the dashboard numbers.

    Disconnect count and total downtime come from the persistent history plus
    the outage in progress, so clearing the history resets those counters.
    """

    def __init__(
        self,
        history: OutageHistory,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self.history = history
        self._clock = clock
        self._wall = wall_clock
        self.state = ConnectionState.UNKNOWN
        self.latency_ms: float | None = None
        self.last_disconnect: datetime | None = None
        self.last_reconnect: datetime | None = None
        self.last_outage_duration: float | None = None
        self._online_since: float | None = None
        self._offline_since: float | None = None
        self._offline_wall: datetime | None = None
        entries = history.entries
        if entries:
            self.last_disconnect = entries[-1].disconnected_at
            self.last_reconnect = entries[-1].reconnected_at
            self.last_outage_duration = entries[-1].duration

    def mark_online(self) -> HistoryEntry | None:
        """Record ONLINE. Returns the finished outage entry when this was a reconnect."""
        now = self._clock()
        entry = None
        if self.state is ConnectionState.OFFLINE and self._offline_since is not None:
            entry = HistoryEntry(self._offline_wall, self._wall(), max(0.0, now - self._offline_since))
            self.history.add(entry)
            self.last_reconnect = entry.reconnected_at
            self.last_outage_duration = entry.duration
        self.state = ConnectionState.ONLINE
        self._online_since = now
        self._offline_since = None
        self._offline_wall = None
        return entry

    def mark_offline(self) -> datetime:
        self.state = ConnectionState.OFFLINE
        self._offline_since = self._clock()
        self._offline_wall = self._wall()
        self.last_disconnect = self._offline_wall
        self._online_since = None
        self.latency_ms = None
        return self._offline_wall

    def history_cleared(self) -> None:
        self.last_reconnect = None
        self.last_outage_duration = None
        self.last_disconnect = self._offline_wall

    @property
    def outage_started_at(self) -> datetime | None:
        return self._offline_wall

    def uptime(self) -> float | None:
        if self._online_since is None:
            return None
        return self._clock() - self._online_since

    def current_downtime(self) -> float | None:
        if self._offline_since is None:
            return None
        return self._clock() - self._offline_since

    def disconnect_count(self) -> int:
        return len(self.history) + (1 if self._offline_since is not None else 0)

    def total_downtime(self) -> float:
        return self.history.total_downtime + (self.current_downtime() or 0.0)
