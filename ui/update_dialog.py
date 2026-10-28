from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from services import update_service as us
from services.update_service import UpdateService
from utils.formatting import format_size


class UpdateDialog(QDialog):
    """Release notes + Download / Install flow. Follows the UpdateService state."""

    def __init__(self, updater: UpdateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.updater = updater
        self.setWindowTitle("Software Update")
        self.setMinimumSize(520, 420)

        self.title = QLabel()
        self.title.setObjectName("sectionTitle")
        self.title.setStyleSheet("font-size: 18px;")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("muted")
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(False)
        self.notes.setOpenLinks(False)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.status = QLabel()
        self.status.setWordWrap(True)

        self.skip_button = QPushButton("Skip this version")
        self.later_button = QPushButton("Later")
        self.primary = QPushButton("Download and install")
        self.primary.setObjectName("primary")
        self.skip_button.clicked.connect(self._skip)
        self.later_button.clicked.connect(self.close)
        self.primary.clicked.connect(self._primary_clicked)

        buttons = QHBoxLayout()
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.primary)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.notes, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

        updater.state_changed.connect(lambda _s: self.refresh())
        updater.progress.connect(self._on_progress)
        self.refresh()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.progress.setFormat(f"{format_size(done)} of {format_size(total)}")

    def _skip(self) -> None:
        self.updater.skip_version()
        self.close()

    def _primary_clicked(self) -> None:
        state = self.updater.state
        if state in (us.AVAILABLE, us.ERROR):
            self.updater.download()
        elif state == us.DOWNLOADING:
            self.updater.cancel_download()
        elif state == us.READY:
            self.updater.install()

    def refresh(self) -> None:
        u = self.updater
        state = u.state
        info = u.info
        if info is not None:
            self.title.setText(f"Net Watcher {info.version} is available")
            self.subtitle.setText(
                f"You have {u.current_version}. Download size: {format_size(info.asset.size)}"
                + (f" · released {info.release.released[:10]}" if info.release.released else "")
            )
            self.notes.setMarkdown(info.release.notes or "No release notes provided.")
        else:
            self.title.setText("Net Watcher is up to date")
            self.subtitle.setText(f"You have version {u.current_version}.")
            self.notes.setMarkdown("")

        self.progress.setVisible(state == us.DOWNLOADING)
        self.skip_button.setVisible(info is not None and state in (us.AVAILABLE, us.ERROR))
        self.later_button.setEnabled(state != us.INSTALLING)
        self.primary.setVisible(info is not None)
        self.primary.setEnabled(state != us.INSTALLING)
        self.primary.setText(
            {
                us.DOWNLOADING: "Cancel download",
                us.READY: "Install and restart",
                us.INSTALLING: "Installing…",
                us.ERROR: "Try again",
            }.get(state, "Download and install")
        )
        self.status.setStyleSheet("")
        if state == us.ERROR:
            self.status.setText(u.error)
        elif state == us.READY:
            self.status.setText(
                u.message or "Downloaded and verified. Net Watcher will close, update, and reopen. Your settings and history are kept."
            )
        elif state == us.INSTALLING:
            self.status.setText(u.message or "Installing…")
        else:
            self.status.setText("")
        self.status.setAlignment(Qt.AlignmentFlag.AlignLeft)
