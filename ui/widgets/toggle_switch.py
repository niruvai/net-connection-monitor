from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QWidget


class ToggleSwitch(QAbstractButton):
    """iOS-style on/off switch. Emits the standard ``toggled(bool)`` signal."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)
        self.on_color = QColor("#4C8DFF")
        self.off_color = QColor("#586381")

    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _on_anim(self, value) -> None:
        self._pos = float(value)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        mix = QColor(
            int(self.off_color.red() + (self.on_color.red() - self.off_color.red()) * self._pos),
            int(self.off_color.green() + (self.on_color.green() - self.off_color.green()) * self._pos),
            int(self.off_color.blue() + (self.on_color.blue() - self.off_color.blue()) * self._pos),
        )
        if not self.isEnabled():
            mix.setAlphaF(0.4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix)
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        d = track.height() - 6
        x = track.left() + 3 + (track.width() - d - 6) * self._pos
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, track.top() + 3, d, d))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QColor(255, 255, 255, 120))
            p.drawRoundedRect(track.adjusted(-1, -1, 1, 1), track.height() / 2, track.height() / 2)
        p.end()
