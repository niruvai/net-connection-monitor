from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.history import HistoryEntry
from core.models import ConnectionState
from services.controller import AppController
from ui.theme import palette
from ui.widgets.stat_card import StatCard
from ui.widgets.status_indicator import StatusIndicator
from utils.formatting import (
    format_clock,
    format_duration,
    format_duration_words,
    format_latency,
    format_speed,
)

BACK_BANNER_SECONDS = 10.0


class DashboardPage(QWidget):
    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._back_until = 0.0
        self._back_duration: float | None = None
        self._dark = controller.settings.dark_mode

        self.indicator = StatusIndicator()
        self.headline = QLabel("CHECKING…")
        self.headline.setObjectName("headline")
        self.headline.setWordWrap(True)
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subline = QLabel("")
        self.subline.setObjectName("subline")
        self.subline.setWordWrap(True)
        self.subline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pause_button = QPushButton("Pause monitoring")
        self.pause_button.clicked.connect(controller.toggle_paused)

        hero = QFrame()
        hero.setObjectName("card")
        hero.setMinimumWidth(340)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(8)
        hero_layout.addWidget(self.indicator, 1)
        hero_layout.addWidget(self.headline)
        hero_layout.addWidget(self.subline)
        hero_layout.addSpacing(8)
        hero_layout.addWidget(self.pause_button)

        self.cards = {
            "ping": StatCard("Ping"),
            "ip": StatCard("IP address", value_px=16),
            "download": StatCard("Download"),
            "upload": StatCard("Upload"),
            "uptime": StatCard("Uptime"),
            "outage": StatCard("Current outage"),
            "disconnects": StatCard("Disconnects"),
            "total": StatCard("Total downtime"),
            "last_disconnect": StatCard("Last disconnect", value_px=16),
            "last_reconnect": StatCard("Last reconnect", value_px=16),
        }
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, i // 2, i % 2)
            grid.setRowStretch(i // 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(hero, 4)
        body.addLayout(grid, 5)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addWidget(title)
        root.addLayout(body, 1)

        controller.state_changed.connect(lambda _s: self.refresh())
        controller.paused_changed.connect(lambda _p: self.refresh())
        controller.went_offline.connect(lambda _w: self._reset_back_banner())
        controller.reconnected.connect(self._on_reconnected)
        controller.latency_updated.connect(self._set_latency)
        controller.throughput_updated.connect(self._set_throughput)
        controller.ip_updated.connect(self._set_ip)
        controller.history_changed.connect(self.refresh)

        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.set_dark(self._dark)
        self.refresh()

    def _on_tick(self) -> None:
        if self.isVisible():
            self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    # ----- reactions -----

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.indicator.set_dark(dark)
        self.refresh()

    def _reset_back_banner(self) -> None:
        self._back_until = 0.0
        self.refresh()

    def _on_reconnected(self, entry: HistoryEntry) -> None:
        self._back_until = time.monotonic() + BACK_BANNER_SECONDS
        self._back_duration = entry.duration
        self.refresh()

    def _set_latency(self, ms) -> None:
        self.cards["ping"].set_value(format_latency(ms))

    def _set_throughput(self, down: float, up: float) -> None:
        self.cards["download"].set_value(format_speed(down))
        self.cards["upload"].set_value(format_speed(up))

    def _set_ip(self, public_ip, local_ip) -> None:
        self.cards["ip"].set_value(public_ip or local_ip or "—")
        hint = ""
        if public_ip and local_ip:
            hint = f"Local: {local_ip}"
        elif local_ip:
            hint = "Local address"
        self.cards["ip"].set_hint(hint)
        self.cards["ip"].set_tooltip(
            "\n".join(x for x in (f"Public: {public_ip}" if public_ip else "", f"Local: {local_ip}" if local_ip else "") if x)
        )

    def display_state(self) -> str:
        if self.controller.paused:
            return "paused"
        return self.controller.state.value

    def refresh(self) -> None:
        c = self.controller
        s = c.session
        state = self.display_state()
        p = palette(self._dark)
        self.indicator.set_state(state)
        color = {"online": p.online, "offline": p.offline}.get(state, p.muted)

        if state == "paused":
            text, sub = "MONITORING PAUSED", "Resume to start checking your connection again."
            if s.state is ConnectionState.OFFLINE:
                sub = "The last known state was OFFLINE. Resume to re-check."
        elif state == "offline":
            text = "INTERNET DISCONNECTED"
            sub = f"Down for {format_duration(s.current_downtime())} · since {format_clock(s.outage_started_at)}"
        elif state == "online":
            if time.monotonic() < self._back_until:
                text = "INTERNET IS BACK! 😂"
                sub = f"It was gone for {format_duration_words(self._back_duration)}"
            else:
                text = "ONLINE"
                sub = f"Connected for {format_duration(s.uptime())}"
        else:
            text, sub = "CHECKING…", "Testing your connection"
        self.headline.setText(text)
        self.headline.setStyleSheet(f"color: {color};")
        self.subline.setText(sub)
        self.pause_button.setText("Resume monitoring" if c.paused else "Pause monitoring")
        wanted = "primary" if c.paused else ""
        if self.pause_button.objectName() != wanted:
            self.pause_button.setObjectName(wanted)
            self.pause_button.style().unpolish(self.pause_button)
            self.pause_button.style().polish(self.pause_button)

        k = self.cards
        k["uptime"].set_value(format_duration(s.uptime()) if s.uptime() is not None else "—")
        outage = s.current_downtime()
        k["outage"].set_value(format_duration(outage) if outage is not None else "—")
        k["disconnects"].set_value(str(s.disconnect_count()))
        k["total"].set_value(format_duration(s.total_downtime()))
        k["last_disconnect"].set_value(format_clock(s.last_disconnect))
        k["last_reconnect"].set_value(format_clock(s.last_reconnect))
        if state == "offline":
            k["ping"].set_value(format_latency(None))
