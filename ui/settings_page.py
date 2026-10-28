from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.settings import INTERVAL_RANGE
from core.version import __version__
from services.audio_service import SOUND_FILTER
from services.controller import AppController
from ui.widgets.toggle_switch import ToggleSwitch
from utils.paths import logs_dir


def _row(title: str, description: str, control: QWidget | None = None, *, stretch_control: bool = False) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 6, 0, 6)
    layout.setSpacing(16)
    text = QVBoxLayout()
    text.setSpacing(1)
    t = QLabel(title)
    t.setObjectName("rowTitle")
    text.addWidget(t)
    if description:
        d = QLabel(description)
        d.setObjectName("rowDesc")
        d.setWordWrap(True)
        text.addWidget(d)
    layout.addLayout(text, 2)
    if control is not None:
        layout.addWidget(control, 3 if stretch_control else 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
    return row


def _section(title: str, rows: list[QWidget]) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 12)
    layout.setSpacing(4)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    for row in rows:
        layout.addWidget(row)
    return card


class SoundPicker(QWidget):
    """File path field with Browse / Test / Reset buttons for one alert sound."""

    def __init__(self, controller: AppController, kind: str, setting: str) -> None:
        super().__init__()
        self.controller, self.kind, self.setting = controller, kind, setting
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setMinimumWidth(180)
        browse = QPushButton("Browse…")
        test = QPushButton("Test")
        reset = QPushButton("Default")
        browse.clicked.connect(self._browse)
        test.clicked.connect(lambda: controller.test_sound(kind))
        reset.clicked.connect(lambda: controller.update_settings(**{setting: ""}))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for w in (self.path, browse, test, reset):
            layout.addWidget(w)
        self.refresh()

    def refresh(self) -> None:
        custom = getattr(self.controller.settings, self.setting)
        self.path.setText(Path(custom).name if custom else "Default sound")
        self.path.setToolTip(custom or str(self.controller.audio.resolve(self.kind)))

    def _browse(self) -> None:
        start = getattr(self.controller.settings, self.setting) or str(Path.home())
        filename, _ = QFileDialog.getOpenFileName(self, "Choose sound", start, SOUND_FILTER)
        if filename:
            self.controller.update_settings(**{self.setting: filename})


class SettingsPage(QWidget):
    check_updates_requested = Signal()

    def __init__(self, controller: AppController, updater=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.updater = updater
        s = controller.settings
        self._loading = True

        self.interval = QDoubleSpinBox()
        self.interval.setRange(*INTERVAL_RANGE)
        self.interval.setSingleStep(0.5)
        self.interval.setDecimals(1)
        self.interval.setSuffix(" s")
        self.interval.setKeyboardTracking(False)
        self.interval.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.interval.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.interval.setFixedWidth(84)
        interval_box = QWidget()
        ib = QHBoxLayout(interval_box)
        ib.setContentsMargins(0, 0, 0, 0)
        ib.setSpacing(6)
        for symbol, direction in (("−", -1), ("+", 1)):
            step = QPushButton(symbol)
            step.setObjectName("step")
            step.setAutoRepeat(True)
            step.clicked.connect(lambda _=False, d=direction: self.interval.stepBy(d))
            ib.addWidget(step)
            if direction < 0:
                ib.addWidget(self.interval)

        self.auto_start = ToggleSwitch()
        self.launch_login = ToggleSwitch()
        self.sounds = ToggleSwitch()
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setMinimumWidth(200)
        self.volume_label = QLabel()
        self.volume_label.setMinimumWidth(40)
        self.offline_picker = SoundPicker(controller, "offline", "offline_sound")
        self.reconnect_picker = SoundPicker(controller, "reconnect", "reconnect_sound")
        self.notifications = ToggleSwitch()
        test_notification = QPushButton("Send test")
        test_notification.clicked.connect(controller.test_notification)
        self.dark = ToggleSwitch()
        self.tray_close = ToggleSwitch()
        open_logs = QPushButton("Open folder")
        open_logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir()))))

        volume_box = QWidget()
        vb = QHBoxLayout(volume_box)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.addWidget(self.volume)
        vb.addWidget(self.volume_label)

        notif_box = QWidget()
        nb = QHBoxLayout(notif_box)
        nb.setContentsMargins(0, 0, 0, 0)
        nb.setSpacing(10)
        nb.addWidget(test_notification)
        nb.addWidget(self.notifications)

        content = QWidget()
        content.setObjectName("scrollBody")
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(14)
        col.addWidget(
            _section(
                "Monitoring",
                [
                    _row("Check interval", "How often connectivity is tested. A drop is confirmed with a quick re-check.", interval_box),
                    _row("Start monitoring automatically", "Begin checking as soon as Net Watcher opens.", self.auto_start),
                    _row("Start with Windows / macOS", "Launch minimized to the tray when you sign in.", self.launch_login),
                ],
            )
        )
        col.addWidget(
            _section(
                "Sounds",
                [
                    _row("Enable sounds", "Play an alert when the connection drops or returns.", self.sounds),
                    _row("Master volume", "", volume_box),
                    _row("Offline sound", "Played once when the internet disconnects.", self.offline_picker, stretch_control=True),
                    _row("Reconnect sound", "Played once when the internet is back.", self.reconnect_picker, stretch_control=True),
                ],
            )
        )
        col.addWidget(
            _section(
                "Notifications and window",
                [
                    _row("Desktop notifications", "Show a system notification on disconnect and reconnect.", notif_box),
                    _row("Minimize to tray on close", "Keep monitoring in the background when the window is closed.", self.tray_close),
                    _row("Dark mode", "Switch between the dark and light theme.", self.dark),
                ],
            )
        )
        self.auto_updates = ToggleSwitch()
        self.update_status = QLabel("")
        self.update_status.setObjectName("rowDesc")
        self.update_status.setWordWrap(True)
        self.check_updates_button = QPushButton("Check now")
        if updater is not None:
            update_box = QWidget()
            ub = QHBoxLayout(update_box)
            ub.setContentsMargins(0, 0, 0, 0)
            ub.addWidget(self.check_updates_button)
            col.addWidget(
                _section(
                    "Updates",
                    [
                        _row("Current version", f"Net Watcher {__version__}", update_box),
                        self.update_status,
                        _row("Check for updates automatically", "Looks for a new release at startup and every few hours.", self.auto_updates),
                    ],
                )
            )
            self.check_updates_button.clicked.connect(self._check_updates)
            self.auto_updates.toggled.connect(lambda v: self._set(auto_check_updates=v))
            updater.state_changed.connect(lambda _s: self._refresh_update_status())
            self._refresh_update_status()
        col.addWidget(_section("Diagnostics", [_row("Log files", "Connection events and errors are logged here.", open_logs)]))
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 20, 12)
        root.setSpacing(14)
        root.addWidget(title)
        root.addWidget(scroll, 1)

        self.interval.valueChanged.connect(lambda v: self._set(check_interval=v))
        self.auto_start.toggled.connect(lambda v: self._set(auto_start_monitoring=v))
        self.launch_login.toggled.connect(lambda v: self._set(launch_at_login=v))
        self.sounds.toggled.connect(lambda v: self._set(sounds_enabled=v))
        self.volume.valueChanged.connect(self._on_volume)
        self.volume.sliderReleased.connect(lambda: controller.test_sound("reconnect"))
        self.notifications.toggled.connect(lambda v: self._set(notifications_enabled=v))
        self.dark.toggled.connect(lambda v: self._set(dark_mode=v))
        self.tray_close.toggled.connect(lambda v: self._set(minimize_to_tray_on_close=v))
        controller.settings_changed.connect(self.load)
        self.load(s)

    def _check_updates(self) -> None:
        self.check_updates_requested.emit()

    def _refresh_update_status(self) -> None:
        u = self.updater
        self.update_status.setText(u.status_text())
        from services.update_service import CHECKING, DOWNLOADING, INSTALLING

        self.check_updates_button.setEnabled(u.available and u.state not in (CHECKING, DOWNLOADING, INSTALLING))

    def _set(self, **changes) -> None:
        if not self._loading:
            self.controller.update_settings(**changes)

    def _on_volume(self, value: int) -> None:
        self.volume_label.setText(f"{value}%")
        self._set(volume=value)

    def load(self, s) -> None:
        self._loading = True
        try:
            self.interval.setValue(s.check_interval)
            self.auto_start.setChecked(s.auto_start_monitoring)
            self.launch_login.setChecked(s.launch_at_login)
            self.sounds.setChecked(s.sounds_enabled)
            self.volume.setValue(s.volume)
            self.volume_label.setText(f"{s.volume}%")
            self.notifications.setChecked(s.notifications_enabled)
            self.dark.setChecked(s.dark_mode)
            self.tray_close.setChecked(s.minimize_to_tray_on_close)
            self.auto_updates.setChecked(s.auto_check_updates)
            self.offline_picker.refresh()
            self.reconnect_picker.refresh()
        finally:
            self._loading = False
