"""Marca Valkyrium · by Pinalo — colores y tipografía fija."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# —— Paleta ——
PURPLE = "#c08bff"  # abismo / Valkyrium
PURPLE_DEEP = "#9b6dff"
PURPLE_DIM = "#6e4fa8"
BLUE_P = "#4dabff"  # azul del icono P
BLUE_TP = "#7ec8ff"
BLUE_DEEP = "#1f6feb"
BG = "#0c0e16"
BG_CARD = "#14121f"
BG_ELEVATED = "#1a1628"
BORDER = "#2e2642"
BORDER_GLOW = "#5b3d8a"
TEXT = "#eef0f7"
TEXT_MUTED = "#9aa0b8"
TEXT_DIM = "#6f7690"
OK = "#5fe08a"
WARN = "#ffd54a"
DANGER = "#ff6b7a"

# —— Tipografía fija (Windows) ——
# Display = marca / títulos · UI = cuerpo · Mono = #TP / timers
_FONT_DISPLAY = ("Bahnschrift", "Segoe UI Semibold", "Segoe UI")
_FONT_UI = ("Segoe UI", "Bahnschrift", "Arial")
_FONT_MONO = ("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New")


def _font(families: tuple[str, ...], size: int, weight: QFont.Weight) -> QFont:
    f = QFont(families[0], size, weight)
    f.setFamilies(list(families))
    f.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    return f


def font_display(size: int = 12, weight: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    return _font(_FONT_DISPLAY, size, weight)


def font_ui(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    return _font(_FONT_UI, size, weight)


def font_mono(size: int = 10, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    return _font(_FONT_MONO, size, weight)


def qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)


# CSS font stacks (QSS)
CSS_UI = '"Segoe UI", "Bahnschrift", sans-serif'
CSS_DISPLAY = '"Bahnschrift", "Segoe UI Semibold", "Segoe UI", sans-serif'
CSS_MONO = '"Cascadia Mono", "Cascadia Code", "Consolas", monospace'
