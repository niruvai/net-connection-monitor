"""Desktop notifications through the system tray icon (works on Windows and macOS)."""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtWidgets import QSystemTrayIcon

log = logging.getLogger(__name__)


class NotificationService:
    def __init__(self) -> None:
        self.enabled = True
        self._tray: QSystemTrayIcon | None = None
        self.on_notify: Callable[[str, str], None] | None = None  # test/diagnostic hook

    def attach(self, tray: QSystemTrayIcon | None) -> None:
        self._tray = tray

    def notify(self, title: str, message: str, force: bool = False) -> bool:
        if not (self.enabled or force):
            return False
        if self.on_notify:
            self.on_notify(title, message)
        if self._tray is None or not self._tray.isVisible():
            log.info("Notification skipped (no visible tray icon): %s - %s", title, message)
            return False
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.NoIcon, 6000)
        return True
