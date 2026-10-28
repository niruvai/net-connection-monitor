"""Large animated circle that shows the connection state."""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.icons import paint_glyph
from ui.theme import state_color

PULSE_MS = {"online": 2400, "offline": 900}


class StatusIndicator(QWidget):
    """Colored disc with a glyph. State changes cross-fade the color, "pop" the disc and,
    for OFFLINE, shake it; a ring pulses outward while the state is online/offline."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 200)
        self._dark = True
        self._state = "unknown"
        self._color = state_color("unknown")
        self._scale = 1.0
        self._shake = 0.0
        self._pulse = 0.0

        self._color_anim = self._make_anim(450, QEasingCurve.Type.InOutCubic, self._set_color)
        self._pop_anim = self._make_anim(520, QEasingCurve.Type.OutBack, self._set_scale)
        self._shake_anim = self._make_anim(600, QEasingCurve.Type.Linear, self._set_shake)
        self._pulse_anim = self._make_anim(PULSE_MS["online"], QEasingCurve.Type.OutCubic, self._set_pulse)
        self._pulse_anim.setLoopCount(-1)

    @property
    def state(self) -> str:
        return self._state

    def sizeHint(self) -> QSize:
        return QSize(260, 260)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._color = state_color(self._state, dark)
        self.update()

    def set_state(self, state: str, animate: bool = True) -> None:
        if state == self._state:
            return
        previous, self._state = self._state, state
        target = state_color(state, self._dark)
        self._color_anim.stop()
        self._pop_anim.stop()
        self._shake_anim.stop()
        if animate and self.isVisible():
            self._color_anim.setStartValue(self._color)
            self._color_anim.setEndValue(target)
            self._color_anim.start()
            self._pop_anim.setStartValue(0.86)
            self._pop_anim.setEndValue(1.0)
            self._pop_anim.start()
            if state == "offline":
                self._shake_anim.setStartValue(0.0)
                self._shake_anim.setEndValue(1.0)
                self._shake_anim.start()
        else:
            self._color = target
            self._scale = 1.0
        self._configure_pulse(previous)
        self.update()

    def _configure_pulse(self, _previous: str) -> None:
        self._pulse_anim.stop()
        duration = PULSE_MS.get(self._state)
        if duration:
            self._pulse_anim.setDuration(duration)
            self._pulse_anim.setStartValue(0.0)
            self._pulse_anim.setEndValue(1.0)
            self._pulse_anim.start()
        else:
            self._pulse = 0.0

    def _make_anim(self, duration: int, curve: QEasingCurve.Type, setter) -> QVariantAnimation:
        anim = QVariantAnimation(self)
        anim.setDuration(duration)
        anim.setEasingCurve(curve)
        anim.valueChanged.connect(setter)
        return anim

    def _set_color(self, value) -> None:
        self._color = QColor(value)
        self.update()

    def _set_scale(self, value) -> None:
        self._scale = float(value)
        self.update()

    def _set_shake(self, value) -> None:
        self._shake = float(value)
        self.update()

    def _set_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._state in PULSE_MS and self._pulse_anim.state() != QVariantAnimation.State.Running:
            self._pulse_anim.start()

    def hideEvent(self, event) -> None:
        self._pulse_anim.stop()  # no timers burning CPU while minimized to the tray
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        shake = math.sin(self._shake * math.pi * 7) * (1 - self._shake) * side * 0.035
        center = QPointF(self.width() / 2 + shake, self.height() / 2)
        outer = side / 2 - 4
        disc = outer * 0.78 * self._scale
        color = self._color

        if self._state in PULSE_MS:
            ring = QColor(color)
            ring.setAlphaF(max(0.0, 0.55 * (1 - self._pulse)))
            p.setPen(QPen(ring, 3 + 5 * (1 - self._pulse)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            radius = disc * (1.0 + 0.28 * self._pulse)
            p.drawEllipse(center, radius, radius)

        glow = QRadialGradient(center, outer)
        glow_color = QColor(color)
        glow_color.setAlphaF(0.30)
        glow.setColorAt(0.55, glow_color)
        glow_color.setAlphaF(0.0)
        glow.setColorAt(1.0, glow_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(center, outer, outer)

        fill = QRadialGradient(center - QPointF(disc * 0.3, disc * 0.35), disc * 1.5)
        fill.setColorAt(0.0, color.lighter(125))
        fill.setColorAt(1.0, color.darker(115))
        p.setBrush(fill)
        p.drawEllipse(center, disc, disc)

        rim = QColor("white")
        rim.setAlphaF(0.25)
        p.setPen(QPen(rim, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(center, disc * 0.9, disc * 0.9)

        paint_glyph(p, self._state, center, disc * 0.85, QColor("white"))
        p.end()
