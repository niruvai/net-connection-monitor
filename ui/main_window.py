from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.version import __version__
from services import update_service as us
from services.controller import AppController
from services.update_service import UpdateService
from ui.dashboard_page import DashboardPage
from ui.history_page import HistoryPage
from ui.icons import app_icon
from ui.settings_page import SettingsPage
from ui.theme import stylesheet
from ui.tray import TrayController
from ui.update_dialog import UpdateDialog
from utils.paths import APP_NAME

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self, controller: AppController, tray: TrayController | None = None, updater: UpdateService | None = None
    ) -> None:
        super().__init__()
        self.controller = controller
        self.tray = tray
        self.updater = updater
        self._update_dialog: UpdateDialog | None = None
        self._show_dialog_on_found = False
        self._quitting = False
        self._tray_hint_shown = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1120, 720)
        self.setMinimumSize(960, 640)

        self.dashboard = DashboardPage(controller)
        self.history_page = HistoryPage(controller)
        self.settings_page = SettingsPage(controller, updater)
        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        for page in (self.dashboard, self.history_page, self.settings_page):
            self.pages.addWidget(page)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 18)
        side.setSpacing(6)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        tagline = QLabel("Internet connection watchdog")
        tagline.setObjectName("brandSub")
        tagline.setWordWrap(True)
        side.addWidget(brand)
        side.addWidget(tagline)
        side.addSpacing(18)

        self.nav = QButtonGroup(self)
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("Dashboard", "History", "Settings")):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav.addButton(button, index)
            self.nav_buttons.append(button)
            side.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        self.nav.idClicked.connect(self.pages.setCurrentIndex)
        side.addStretch(1)
        self.update_banner = self._build_update_banner()
        side.addWidget(self.update_banner)
        self.version_label = QLabel(f"Version {__version__}")
        self.version_label.setObjectName("brandSub")
        side.addWidget(self.version_label)
        self.footer = QLabel("")
        self.footer.setObjectName("brandSub")
        self.footer.setWordWrap(True)
        side.addWidget(self.footer)

        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        controller.settings_changed.connect(self.apply_settings)
        controller.went_offline.connect(lambda _w: self._attract_attention())
        controller.reconnected.connect(lambda _e: self._attract_attention())
        self.apply_settings(controller.settings)
        if updater is not None:
            updater.state_changed.connect(lambda _s: self._refresh_update_banner())
            updater.update_found.connect(self._on_update_found)
            updater.quit_requested.connect(self.request_quit)
            self.settings_page.check_updates_requested.connect(self.check_for_updates)
            if tray is not None:
                tray.icon.messageClicked.connect(self._on_tray_message_clicked)
        self._refresh_update_banner()

    def _build_update_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("card")
        lay = QVBoxLayout(banner)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        self.update_label = QLabel("")
        self.update_label.setWordWrap(True)
        self.update_label.setObjectName("rowTitle")
        view = QPushButton("View update")
        view.setObjectName("primary")
        view.clicked.connect(self.show_update_dialog)
        lay.addWidget(self.update_label)
        lay.addWidget(view)
        banner.hide()
        return banner

    def _refresh_update_banner(self) -> None:
        u = self.updater
        if u is None or not u.pending:
            self.update_banner.hide()
            return
        text = {
            us.DOWNLOADING: f"Downloading {u.info.version}…",
            us.READY: f"{u.info.version} is ready to install",
            us.INSTALLING: "Installing update…",
        }.get(u.state, f"Update {u.info.version} available")
        self.update_label.setText(text)
        self.update_banner.show()

    def show_update_dialog(self) -> None:
        if self.updater is None:
            return
        if self._update_dialog is None:
            self._update_dialog = UpdateDialog(self.updater, self)
        self._update_dialog.refresh()
        self.show_and_raise()
        self._update_dialog.show()
        self._update_dialog.raise_()

    def check_for_updates(self) -> None:
        """User-initiated check: opens the dialog if something is found."""
        if self.updater is None:
            return
        self._show_dialog_on_found = True
        self.updater.check(manual=True)

    def _on_update_found(self, _info) -> None:
        if self._show_dialog_on_found:
            self._show_dialog_on_found = False
            self.show_update_dialog()

    def _on_tray_message_clicked(self) -> None:
        if self.updater is not None and self.updater.pending:
            self.show_update_dialog()

    def apply_settings(self, settings) -> None:
        app = QApplication.instance()
        sheet = stylesheet(settings.dark_mode)
        if app is not None and app.styleSheet() != sheet:
            app.setStyleSheet(sheet)
        self.dashboard.set_dark(settings.dark_mode)
        tray_note = "Closing the window keeps monitoring in the tray." if settings.minimize_to_tray_on_close else "Closing the window quits the app."
        self.footer.setText(tray_note)

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def request_quit(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    def _attract_attention(self) -> None:
        if self.isVisible() and not self.isActiveWindow():
            QApplication.alert(self, 0)

    def closeEvent(self, event: QCloseEvent) -> None:
        tray_ok = self.tray is not None and self.tray.icon.isVisible()
        if not self._quitting and tray_ok and self.controller.settings.minimize_to_tray_on_close:
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.message(APP_NAME, "Still watching your connection from the system tray.")
            log.info("Window hidden to tray")
            return
        self._quitting = True
        event.accept()
        QApplication.quit()
