"""Marca Valkyrium · by Pinalo — colores del emblema (cian, cobalto, noche)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# —— Paleta del emblema: alas cian, escudo cobalto, fondo noche ——
PURPLE = "#5ad4ff"  # acento (el cian del emblema; el nombre se mantiene)
PURPLE_DEEP = "#2aa8e0"
PURPLE_DIM = "#1a6f99"
BLUE_P = "#8ee9ff"
BLUE_TP = "#b9f4ff"
BLUE_DEEP = "#1578c9"
BG = "#070d18"
BG_CARD = "#0e1828"
BG_ELEVATED = "#142236"
BORDER = "#1e3a56"
BORDER_GLOW = "#3ec8f0"
TEXT = "#f4fbff"
TEXT_MUTED = "#9eb4c8"
TEXT_DIM = "#6d8498"
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
