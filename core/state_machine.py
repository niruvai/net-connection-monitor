"""Debounced ONLINE/OFFLINE state machine.

Pure logic, no threads or I/O, so it is trivial to unit test. A transition is
emitted *only* when the state really changes, which is what guarantees alerts
fire once per outage and once per recovery.
"""
from __future__ import annotations

from core.models import ConnectionState, Transition


class ConnectionStateMachine:
    def __init__(self, failure_threshold: int = 2, success_threshold: int = 1) -> None:
        if failure_threshold < 1 or success_threshold < 1:
            raise ValueError("thresholds must be >= 1")
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.state = ConnectionState.UNKNOWN
        self.consecutive_failures = 0
        self.consecutive_successes = 0

    @property
    def is_verifying_failure(self) -> bool:
        """True while failures are accumulating but OFFLINE is not declared yet."""
        return self.state is not ConnectionState.OFFLINE and self.consecutive_failures > 0

    def update(self, reachable: bool) -> Transition | None:
        if reachable:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            if self.state is not ConnectionState.ONLINE and self.consecutive_successes >= self.success_threshold:
                return self._move(ConnectionState.ONLINE)
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            if self.state is not ConnectionState.OFFLINE and self.consecutive_failures >= self.failure_threshold:
                return self._move(ConnectionState.OFFLINE)
        return None

    def clear_counters(self) -> None:
        """Forget in-flight evidence (e.g. after system sleep) but keep the current state."""
        self.consecutive_failures = 0
        self.consecutive_successes = 0

    def _move(self, new_state: ConnectionState) -> Transition:
        transition = Transition(self.state, new_state)
        self.state = new_state
        return transition
