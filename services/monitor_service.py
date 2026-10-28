"""Qt bridge for the Qt-free ``NetworkMonitor``.

The monitor thread calls plain callbacks; here they become Qt signals. Because
the receivers live in the GUI thread, Qt delivers them through the event queue,
so the worker thread never touches widgets and the GUI never waits on it.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from core.models import CheckResult, ConnectionState, Transition
from core.monitor import Checker, NetworkMonitor


class MonitorService(QObject):
    checked = Signal(object)  # CheckResult
    transitioned = Signal(object, object)  # Transition, CheckResult
    adapter_changed = Signal()

    def __init__(
        self,
        checker: Checker,
        interval: float,
        signature_provider: Optional[callable] = None,
        failure_threshold: int = 2,
        success_threshold: int = 1,
        recheck_delay: float | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        kwargs = {} if recheck_delay is None else {"recheck_delay": recheck_delay}
        self._monitor = NetworkMonitor(
            checker,
            interval=interval,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            on_check=self._emit_check,
            on_transition=self._emit_transition,
            on_adapter_change=self.adapter_changed.emit,
            signature_provider=signature_provider,
            **kwargs,
        )

    def _emit_check(self, result: CheckResult) -> None:
        self.checked.emit(result)

    def _emit_transition(self, transition: Transition, result: CheckResult) -> None:
        self.transitioned.emit(transition, result)

    @property
    def state(self) -> ConnectionState:
        return self._monitor.state

    @property
    def paused(self) -> bool:
        return self._monitor.paused

    @property
    def running(self) -> bool:
        return self._monitor.running

    def start(self, paused: bool = False) -> None:
        self._monitor.start(paused=paused)

    def pause(self) -> None:
        self._monitor.pause()

    def resume(self) -> None:
        self._monitor.resume()

    def check_now(self) -> None:
        self._monitor.check_now()

    def set_interval(self, seconds: float) -> None:
        self._monitor.set_interval(seconds)

    def stop(self) -> None:
        self._monitor.stop()
