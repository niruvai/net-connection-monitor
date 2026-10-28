"""Background network monitor.

``NetworkMonitor`` owns one daemon thread. It knows nothing about Qt: results
are delivered through plain callbacks that run *on the monitor thread*, so a
GUI layer must forward them with thread-safe signals (see
``services/monitor_service.py``).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Hashable, Optional, Protocol

from core.models import CheckResult, ConnectionState, Transition
from core.state_machine import ConnectionStateMachine

log = logging.getLogger(__name__)

RECHECK_DELAY = 0.75  # seconds between confirmation checks after a failed cycle
WAKE_SLICE = 1.0  # how often a sleeping loop looks for adapter changes
SLEEP_GAP_FACTOR = 3.0  # a cycle gap this many intervals long means the machine slept
SLEEP_GAP_MIN = 15.0


class Checker(Protocol):
    def check(self) -> CheckResult: ...


CheckCallback = Callable[[CheckResult], None]
TransitionCallback = Callable[[Transition, CheckResult], None]


class NetworkMonitor:
    def __init__(
        self,
        checker: Checker,
        interval: float = 2.0,
        failure_threshold: int = 2,
        success_threshold: int = 1,
        on_check: Optional[CheckCallback] = None,
        on_transition: Optional[TransitionCallback] = None,
        on_adapter_change: Optional[Callable[[], None]] = None,
        signature_provider: Optional[Callable[[], Hashable]] = None,
        recheck_delay: float = RECHECK_DELAY,
    ) -> None:
        self._checker = checker
        self._interval = max(0.1, float(interval))
        self._machine = ConnectionStateMachine(failure_threshold, success_threshold)
        self._on_check = on_check
        self._on_transition = on_transition
        self._on_adapter_change = on_adapter_change
        self._signature_provider = signature_provider
        self._recheck_delay = recheck_delay

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._paused = threading.Event()
        self._lock = threading.Lock()

    # ----- public control (safe from any thread) -----

    @property
    def state(self) -> ConnectionState:
        return self._machine.state

    @property
    def interval(self) -> float:
        return self._interval

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_interval(self, seconds: float) -> None:
        self._interval = max(0.1, float(seconds))
        self._wake.set()

    def start(self, paused: bool = False) -> None:
        with self._lock:
            if self.running:
                return
            self._stop.clear()
            self._wake.clear()
            if paused:
                self._paused.set()
            else:
                self._paused.clear()
            self._thread = threading.Thread(target=self._run, name="net-monitor", daemon=True)
            self._thread.start()
        log.info("Monitor started (interval=%.1fs, paused=%s)", self._interval, paused)

    def pause(self) -> None:
        if not self._paused.is_set():
            self._paused.set()
            self._wake.set()
            log.info("Monitoring paused")

    def resume(self) -> None:
        if self._paused.is_set():
            self._paused.clear()
            self._machine.clear_counters()
            self._wake.set()
            log.info("Monitoring resumed")

    def check_now(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                log.warning("Monitor thread did not stop within %.1fs", timeout)
        self._thread = None
        log.info("Monitor stopped")

    # ----- thread body -----

    def _run(self) -> None:
        signature = self._read_signature()
        last_cycle = time.time()
        while not self._stop.is_set():
            if self._paused.is_set():
                self._wake.wait()
                self._wake.clear()
                last_cycle = time.time()
                continue

            self._wake.clear()
            now = time.time()
            if now - last_cycle > max(SLEEP_GAP_MIN, self._interval * SLEEP_GAP_FACTOR):
                log.info("Large gap between checks (%.0fs): system likely slept; discarding stale evidence", now - last_cycle)
                self._machine.clear_counters()
            last_cycle = now

            try:
                result = self._checker.check()
            except Exception:
                log.exception("Connectivity check crashed; treating as inconclusive")
                self._wake.wait(self._interval)
                continue

            if self._paused.is_set() or self._stop.is_set():
                continue  # result may be stale if the user paused mid-check

            self._handle_result(result)

            delay = self._interval
            if self._machine.is_verifying_failure:
                delay = min(delay, self._recheck_delay)
            signature = self._sleep(delay, signature)

    def _handle_result(self, result: CheckResult) -> None:
        log.debug("Check: reachable=%s latency=%s [%s]", result.reachable, result.latency_ms, result.summary())
        transition = self._machine.update(result.reachable)
        self._emit(self._on_check, result)
        if transition:
            log.info(
                "Connection state %s -> %s (%s)", transition.previous.value, transition.current.value, result.summary()
            )
            self._emit(self._on_transition, transition, result)

    def _sleep(self, delay: float, signature: Hashable) -> Hashable:
        """Wait up to ``delay`` seconds, waking early on control events or adapter changes."""
        deadline = time.monotonic() + delay
        while not self._wake.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._wake.wait(min(remaining, WAKE_SLICE))
            current = self._read_signature()
            if current != signature:
                log.info("Network adapter configuration changed; re-checking immediately")
                self._emit(self._on_adapter_change)
                return current
        return signature

    def _read_signature(self) -> Hashable:
        if not self._signature_provider:
            return None
        try:
            return self._signature_provider()
        except Exception:
            log.debug("Could not read network signature", exc_info=True)
            return None

    @staticmethod
    def _emit(callback: Optional[Callable], *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            log.exception("Monitor callback failed")
