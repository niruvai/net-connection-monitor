from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from services.controller import AppController
from ui.icons import app_icon, tray_icon
from utils.formatting import format_latency
from utils.paths import APP_NAME


class TrayController(QObject):
    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, controller: AppController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.icon = QSystemTrayIcon(app_icon(), self)

        self.menu = QMenu()
        self.show_action = QAction("Show Net Watcher", self.menu)
        self.pause_action = QAction("Pause Monitoring", self.menu)
        self.sound_action = QAction("Disable Sounds", self.menu)
        self.quit_action = QAction("Exit", self.menu)
        self.menu.addAction(self.show_action)
        self.menu.addSeparator()
        self.menu.addAction(self.pause_action)
        self.menu.addAction(self.sound_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.icon.setContextMenu(self.menu)

        self.show_action.triggered.connect(self.show_requested)
        self.quit_action.triggered.connect(self.quit_requested)
        self.pause_action.triggered.connect(controller.toggle_paused)
        self.sound_action.triggered.connect(self._toggle_sounds)
        self.icon.activated.connect(self._on_activated)

        controller.state_changed.connect(lambda _s: self.refresh())
        controller.paused_changed.connect(lambda _p: self.refresh())
        controller.settings_changed.connect(lambda _s: self.refresh())
        controller.latency_updated.connect(lambda _ms: self._update_tooltip())
        self.refresh()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        self.icon.show()
        self.controller.notifier.attach(self.icon)

    def hide(self) -> None:
        self.icon.hide()
        self.controller.notifier.attach(None)

    def message(self, title: str, text: str) -> None:
        if self.icon.isVisible():
            self.icon.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 4000)

    def display_state(self) -> str:
        return "paused" if self.controller.paused else self.controller.state.value

    def refresh(self) -> None:
        self.icon.setIcon(tray_icon(self.display_state()))
        self.pause_action.setText("Resume Monitoring" if self.controller.paused else "Pause Monitoring")
        self.sound_action.setText("Disable Sounds" if self.controller.settings.sounds_enabled else "Enable Sounds")
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        state = self.display_state()
        labels = {"online": "Online", "offline": "INTERNET DISCONNECTED", "paused": "Monitoring paused", "unknown": "Checking…"}
        text = f"{APP_NAME} — {labels[state]}"
        if state == "online" and self.controller.session.latency_ms is not None:
            text += f" ({format_latency(self.controller.session.latency_ms)})"
        self.icon.setToolTip(text)

    def _toggle_sounds(self) -> None:
        self.controller.set_sounds_enabled(not self.controller.settings.sounds_enabled)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_requested.emit()
