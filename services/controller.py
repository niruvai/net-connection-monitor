"""Application controller: wires the monitor to history, sound, notifications and the UI.

All business rules live here (and in ``core``); widgets only render the
signals and call the public methods.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from core.connectivity import ConnectivityChecker
from core.history import OutageHistory
from core.models import CheckResult, ConnectionState, Transition
from core.session import SessionTracker
from core.settings import Settings, SettingsStore
from services import autostart_service
from services.audio_service import AudioService
from services.monitor_service import MonitorService
from services.network_info import ThroughputSampler, fetch_public_ip, interface_signature, local_ip
from services.notification_service import NotificationService
from utils.formatting import format_clock, format_duration_words

log = logging.getLogger(__name__)

IP_REFRESH_MS = 5 * 60 * 1000
ADAPTER_IP_DELAY_MS = 2500
THROUGHPUT_MS = 1000


class AppController(QObject):
    state_changed = Signal(object)  # ConnectionState (confirmed by the monitor)
    went_offline = Signal(object)  # datetime of the disconnect
    reconnected = Signal(object)  # HistoryEntry
    latency_updated = Signal(object)  # float | None
    throughput_updated = Signal(float, float)  # download B/s, upload B/s
    ip_updated = Signal(object, object)  # public ip | None, local ip | None
    paused_changed = Signal(bool)
    settings_changed = Signal(object)  # Settings
    history_changed = Signal()
    _public_ip_fetched = Signal(object)

    def __init__(
        self,
        store: SettingsStore,
        history: OutageHistory,
        checker=None,
        audio: AudioService | None = None,
        notifier: NotificationService | None = None,
        autostart=autostart_service,
        signature_provider=interface_signature,
        ip_fetcher=fetch_public_ip,
        sampler: ThroughputSampler | None = None,
        recheck_delay: float | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = store.load()
        self.history = history
        self.session = SessionTracker(history)
        self.audio = audio or AudioService(self)
        self.notifier = notifier or NotificationService()
        self._autostart = autostart
        self._ip_fetcher = ip_fetcher
        self._sampler = sampler or ThroughputSampler()
        self.public_ip: str | None = None
        self.local_ip: str | None = None
        self._fetching_ip = False

        self.monitor = MonitorService(
            checker or ConnectivityChecker(),
            interval=self.settings.check_interval,
            signature_provider=signature_provider,
            recheck_delay=recheck_delay,
            parent=self,
        )
        self.monitor.checked.connect(self._on_checked)
        self.monitor.transitioned.connect(self._on_transition)
        self.monitor.adapter_changed.connect(self._on_adapter_changed)
        self._public_ip_fetched.connect(self._on_public_ip)

        self._throughput_timer = QTimer(self)
        self._throughput_timer.setInterval(THROUGHPUT_MS)
        self._throughput_timer.timeout.connect(self._sample_throughput)
        self._ip_timer = QTimer(self)
        self._ip_timer.setInterval(IP_REFRESH_MS)
        self._ip_timer.timeout.connect(self.refresh_ip)

        self._apply_runtime_settings()

    # ----- lifecycle -----

    def start(self) -> None:
        paused = not self.settings.auto_start_monitoring
        self.monitor.start(paused=paused)
        self._throughput_timer.start()
        self._ip_timer.start()
        self.local_ip = local_ip()
        if self.settings.launch_at_login:
            self._autostart.set_enabled(True)  # re-assert in case the app was moved
        self.paused_changed.emit(paused)
        log.info("Net Watcher started (monitoring %s)", "paused" if paused else "active")

    def shutdown(self) -> None:
        log.info("Shutting down")
        self._throughput_timer.stop()
        self._ip_timer.stop()
        self.monitor.stop()
        self.audio.stop()
        self.store.save(self.settings)

    # ----- state exposed to the UI -----

    @property
    def paused(self) -> bool:
        return self.monitor.paused

    @property
    def state(self) -> ConnectionState:
        return self.session.state

    # ----- user actions -----

    def set_paused(self, paused: bool) -> None:
        if paused == self.monitor.paused and self.monitor.running:
            return
        if not self.monitor.running:
            self.monitor.start(paused=paused)
        elif paused:
            self.monitor.pause()
        else:
            self.monitor.resume()
        self.paused_changed.emit(paused)

    def toggle_paused(self) -> None:
        self.set_paused(not self.paused)

    def update_settings(self, **changes) -> None:
        new = Settings.from_dict({**self.settings.to_dict(), **changes})
        old, self.settings = self.settings, new
        self.store.save(new)
        self._apply_runtime_settings()
        if old.check_interval != new.check_interval:
            log.info("Check interval changed to %.1fs", new.check_interval)
        if old.launch_at_login != new.launch_at_login:
            if not self._autostart.set_enabled(new.launch_at_login):
                self.settings.launch_at_login = old.launch_at_login
                self.store.save(self.settings)
        self.settings_changed.emit(self.settings)

    def set_sounds_enabled(self, enabled: bool) -> None:
        self.update_settings(sounds_enabled=enabled)

    def clear_history(self) -> None:
        self.history.clear()
        self.session.history_cleared()
        log.info("History cleared")
        self.history_changed.emit()

    def test_sound(self, kind: str) -> None:
        self.audio.play(kind, force=True)

    def test_notification(self) -> None:
        self.notifier.notify("Net Watcher", "Desktop notifications are working.", force=True)

    def refresh_ip(self) -> None:
        self.local_ip = local_ip()
        if self._fetching_ip or self.session.state is ConnectionState.OFFLINE:
            self.ip_updated.emit(self.public_ip, self.local_ip)
            return
        self._fetching_ip = True
        threading.Thread(target=self._fetch_ip_worker, name="ip-lookup", daemon=True).start()

    # ----- internals -----

    def _apply_runtime_settings(self) -> None:
        s = self.settings
        self.audio.configure(s.sounds_enabled, s.volume, s.offline_sound, s.reconnect_sound)
        self.notifier.enabled = s.notifications_enabled
        self.monitor.set_interval(s.check_interval)

    def _fetch_ip_worker(self) -> None:
        try:
            self._public_ip_fetched.emit(self._ip_fetcher())
        except Exception:
            log.debug("Public IP lookup failed", exc_info=True)
            self._public_ip_fetched.emit(None)

    def _on_public_ip(self, ip) -> None:
        self._fetching_ip = False
        if ip:
            self.public_ip = ip
        self.ip_updated.emit(self.public_ip, self.local_ip)

    def _sample_throughput(self) -> None:
        sample = self._sampler.sample()
        if sample:
            self.throughput_updated.emit(*sample)

    def _on_checked(self, result: CheckResult) -> None:
        if self.session.state is ConnectionState.OFFLINE:
            self.session.latency_ms = None
        elif result.reachable:
            self.session.latency_ms = result.latency_ms
        # An unreachable cycle that is still being confirmed keeps the last known latency.
        self.latency_updated.emit(self.session.latency_ms)

    def _on_adapter_changed(self) -> None:
        self._sampler.reset()
        QTimer.singleShot(ADAPTER_IP_DELAY_MS, self.refresh_ip)

    def _on_transition(self, transition: Transition, result: CheckResult) -> None:
        if transition.went_offline:
            when = self.session.mark_offline()
            self.latency_updated.emit(None)
            log.warning("INTERNET DISCONNECTED at %s", when.isoformat(timespec="seconds"))
            self.audio.play("offline")
            self.notifier.notify("INTERNET DISCONNECTED", f"Connection lost at {format_clock(when)}.")
            self.went_offline.emit(when)
        elif transition.came_online:
            entry = self.session.mark_online()
            if transition.is_reconnect and entry is not None:
                log.warning("INTERNET IS BACK after %s", format_duration_words(entry.duration))
                self.audio.play("reconnect")
                self.notifier.notify(
                    "INTERNET IS BACK! 😂", f"Offline for {format_duration_words(entry.duration)}."
                )
                self.history_changed.emit()
                self.reconnected.emit(entry)
            self.session.latency_ms = result.latency_ms
            self.latency_updated.emit(result.latency_ms)
            self.refresh_ip()
        self.state_changed.emit(self.session.state)
