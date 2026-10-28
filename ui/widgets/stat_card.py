from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class StatCard(QFrame):
    """Small titled tile showing one metric."""

    def __init__(self, title: str, value: str = "—", hint: str = "", value_px: int = 22, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self._title = QLabel(title.upper())
        self._title.setObjectName("cardTitle")
        self._value = QLabel(value)
        self._value.setObjectName("cardValue")
        self._value.setStyleSheet(f"font-size: {value_px}px;")
        self._hint = QLabel(hint)
        self._hint.setObjectName("cardHint")
        self._hint.setVisible(bool(hint))
        for w in (self._title, self._value, self._hint):
            layout.addWidget(w)
        layout.addStretch(1)

    def set_value(self, text: str) -> None:
        if self._value.text() != text:
            self._value.setText(text)

    def set_hint(self, text: str) -> None:
        self._hint.setText(text)
        self._hint.setVisible(bool(text))

    def set_tooltip(self, text: str) -> None:
        self.setToolTip(text)
