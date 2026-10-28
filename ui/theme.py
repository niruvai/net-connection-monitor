"""Colors and the Qt style sheet for dark / light mode."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    bg: str
    sidebar: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    online: str = "#22C55E"
    offline: str = "#EF4444"
    neutral: str = "#8190AE"


DARK = Palette(
    bg="#0E1220", sidebar="#0A0E1A", surface="#171D30", surface_alt="#1E2640", border="#2A3452",
    text="#E8ECF8", muted="#8D98B8", accent="#4C8DFF", accent_text="#FFFFFF",
)
LIGHT = Palette(
    bg="#F1F4FA", sidebar="#E6EAF4", surface="#FFFFFF", surface_alt="#EEF2FA", border="#D9DFEC",
    text="#18203A", muted="#667291", accent="#2F6BFF", accent_text="#FFFFFF",
)

STATE_NAMES = ("online", "offline", "paused", "unknown")


def palette(dark: bool) -> Palette:
    return DARK if dark else LIGHT


def state_color(state: str, dark: bool = True) -> QColor:
    p = palette(dark)
    return QColor({"online": p.online, "offline": p.offline}.get(state, p.neutral))


def stylesheet(dark: bool) -> str:
    p = palette(dark)
    return f"""
* {{ font-size: 13px; }}
QWidget {{ background: transparent; color: {p.text}; }}
QMainWindow, QDialog, #root, #pages, #scrollBody {{ background: {p.bg}; }}
QScrollArea {{ border: none; background: transparent; }}
QToolTip {{ background: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border}; padding: 4px 6px; }}

#sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#brand {{ font-size: 18px; font-weight: 700; }}
#brandSub, #muted {{ color: {p.muted}; }}
#navButton {{
    background: transparent; text-align: left; padding: 11px 16px; border: none; border-radius: 10px;
    color: {p.muted}; font-weight: 600; font-size: 14px;
}}
#navButton:hover {{ background: {p.surface_alt}; color: {p.text}; }}
#navButton:checked {{ background: {p.accent}; color: {p.accent_text}; }}

#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
#card QLabel {{ background: transparent; }}
#cardTitle {{ color: {p.muted}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
#cardValue {{ font-size: 22px; font-weight: 700; }}
#cardHint {{ color: {p.muted}; font-size: 11px; }}
#pageTitle {{ font-size: 24px; font-weight: 800; }}
#sectionTitle {{ font-size: 14px; font-weight: 700; }}
#headline {{ font-size: 24px; font-weight: 800; }}
#subline {{ color: {p.muted}; font-size: 14px; }}
#rowTitle {{ font-weight: 600; font-size: 14px; }}
#rowDesc {{ color: {p.muted}; font-size: 12px; }}
#emptyState {{ color: {p.muted}; font-size: 14px; }}

QPushButton {{
    background: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border};
    border-radius: 10px; padding: 8px 16px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {p.accent}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled {{ color: {p.muted}; }}
QPushButton#primary {{ background: {p.accent}; color: {p.accent_text}; border: none; }}
QPushButton#primary:hover {{ background: {p.accent}; }}
QPushButton#danger {{ color: {p.offline}; }}
QPushButton#danger:hover {{ border-color: {p.offline}; }}

QLineEdit, QDoubleSpinBox, QSpinBox {{
    background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px;
    padding: 6px 10px; selection-background-color: {p.accent};
}}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {p.accent}; }}

QPushButton#step {{ padding: 0; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; font-size: 16px; }}

QSlider::groove:horizontal {{ height: 6px; background: {p.border}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; background: #FFFFFF; border: 2px solid {p.accent};
}}

QTableWidget {{
    background: {p.surface}; alternate-background-color: {p.surface_alt}; border: 1px solid {p.border};
    border-radius: 12px; gridline-color: transparent; outline: 0;
}}
QTableWidget::item {{ padding: 8px 10px; border: none; }}
QTableWidget::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
QHeaderView::section {{
    background: {p.surface}; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
    padding: 10px; font-weight: 700; font-size: 11px;
}}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; padding: 6px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
QMessageBox {{ background: {p.bg}; }}
"""
