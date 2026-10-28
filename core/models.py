"""Plain data types shared across the app. No Qt imports here."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class ConnectionState(str, Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass(frozen=True)
class ProbeResult:
    probe: str
    ok: bool
    latency_ms: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one connectivity check cycle (all probes combined)."""

    reachable: bool
    latency_ms: float | None = None
    probes: tuple[ProbeResult, ...] = ()
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> str:
        parts = [
            f"{p.probe}={'ok' if p.ok else 'fail'}" + (f"({p.error})" if p.error and not p.ok else "")
            for p in self.probes
        ]
        return ", ".join(parts) if parts else "no probes completed"


@dataclass(frozen=True)
class Transition:
    """A change of connection state reported by the state machine."""

    previous: ConnectionState
    current: ConnectionState

    @property
    def went_offline(self) -> bool:
        return self.current is ConnectionState.OFFLINE

    @property
    def came_online(self) -> bool:
        return self.current is ConnectionState.ONLINE

    @property
    def is_reconnect(self) -> bool:
        """True only for OFFLINE -> ONLINE (the first ever ONLINE is not a reconnect)."""
        return self.previous is ConnectionState.OFFLINE and self.current is ConnectionState.ONLINE
