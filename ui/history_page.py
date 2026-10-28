from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.controller import AppController
from utils.formatting import format_datetime, format_duration, format_duration_words

COLUMNS = ("DISCONNECTED", "RECONNECTED", "DOWNTIME")


class HistoryPage(QWidget):
    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller

        title = QLabel("History")
        title.setObjectName("pageTitle")
        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        self.clear_button = QPushButton("Clear history")
        self.clear_button.setObjectName("danger")
        self.clear_button.clicked.connect(self._confirm_clear)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(title)
        titles.addWidget(self.summary)
        header.addLayout(titles, 1)
        header.addWidget(self.clear_button, 0, Qt.AlignmentFlag.AlignTop)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.empty = QLabel("No outages recorded yet.\nEvery disconnect and reconnect will show up here.")
        self.empty.setObjectName("emptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        host = QWidget()
        self._stack = QStackedLayout(host)
        self._stack.addWidget(self.empty)
        self._stack.addWidget(self.table)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addLayout(header)
        root.addWidget(host, 1)

        controller.history_changed.connect(self.refresh)
        controller.went_offline.connect(lambda _w: self.refresh())
        controller.state_changed.connect(lambda _s: self.refresh())
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.refresh()

    def _on_tick(self) -> None:
        if self.isVisible() and self.controller.session.current_downtime() is not None:
            self.refresh()

    def refresh(self) -> None:
        entries = list(reversed(self.controller.history.entries))
        session = self.controller.session
        ongoing = session.outage_started_at if session.current_downtime() is not None else None

        rows = []
        if ongoing is not None:
            rows.append((format_datetime(ongoing), "Still offline…", format_duration(session.current_downtime())))
        rows.extend(
            (format_datetime(e.disconnected_at), format_datetime(e.reconnected_at), format_duration(e.duration))
            for e in entries
        )
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self._stack.setCurrentWidget(self.table if rows else self.empty)
        self.clear_button.setEnabled(bool(entries))

        count = len(entries)
        if count:
            self.summary.setText(
                f"{count} recorded outage{'s' if count != 1 else ''} · "
                f"{format_duration_words(self.controller.history.total_downtime)} total downtime"
            )
        else:
            self.summary.setText("Nothing recorded")

    def _confirm_clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear history",
            "Delete all recorded outages? Disconnect counters and total downtime will reset too.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.clear_history()
