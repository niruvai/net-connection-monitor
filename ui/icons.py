"""Application and tray icons. File assets win; painted fallbacks keep the app working without them."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from ui.theme import state_color
from utils.paths import resource_path


def paint_glyph(p: QPainter, state: str, center: QPointF, radius: float, color: QColor) -> None:
    """Draw the white symbol (check / cross / pause / dots) used by the dashboard and tray."""
    pen = QPen(color, radius * 0.17, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy, r = center.x(), center.y(), radius
    if state == "online":
        path = QPainterPath(QPointF(cx - 0.45 * r, cy + 0.02 * r))
        path.lineTo(cx - 0.12 * r, cy + 0.35 * r)
        path.lineTo(cx + 0.48 * r, cy - 0.32 * r)
        p.drawPath(path)
    elif state == "offline":
        p.drawLine(QPointF(cx - 0.36 * r, cy - 0.36 * r), QPointF(cx + 0.36 * r, cy + 0.36 * r))
        p.drawLine(QPointF(cx + 0.36 * r, cy - 0.36 * r), QPointF(cx - 0.36 * r, cy + 0.36 * r))
    elif state == "paused":
        p.drawLine(QPointF(cx - 0.22 * r, cy - 0.38 * r), QPointF(cx - 0.22 * r, cy + 0.38 * r))
        p.drawLine(QPointF(cx + 0.22 * r, cy - 0.38 * r), QPointF(cx + 0.22 * r, cy + 0.38 * r))
    else:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for dx in (-0.4, 0.0, 0.4):
            p.drawEllipse(QPointF(cx + dx * r, cy), r * 0.1, r * 0.1)


def painted_state_icon(state: str, size: int = 128) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(state_color(state))
    margin = size * 0.04
    p.drawEllipse(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    paint_glyph(p, state, QPointF(size / 2, size / 2), size * 0.42, QColor("white"))
    p.end()
    return pix


def paint_app_icon(size: int = 512) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    inset = size * 0.04
    body = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    grad = QLinearGradient(body.topLeft(), body.bottomRight())
    grad.setColorAt(0, QColor("#3B82F6"))
    grad.setColorAt(1, QColor("#6D4AFF"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(body, size * 0.22, size * 0.22)

    cx, cy = size / 2, size * 0.68
    pen = QPen(QColor("white"), size * 0.065, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for radius in (0.17, 0.30, 0.43):
        r = size * radius
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 45 * 16, 90 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#4ADE80"))
    p.drawEllipse(QPointF(cx, cy), size * 0.055, size * 0.055)
    p.end()
    return pix


def app_icon() -> QIcon:
    path = resource_path("assets", "icons", "app.png")
    return QIcon(str(path)) if path.is_file() else QIcon(paint_app_icon(256))


def tray_icon(state: str) -> QIcon:
    path = resource_path("assets", "icons", f"tray_{state}.png")
    if path.is_file():
        return QIcon(str(path))
    return QIcon(painted_state_icon(state))
