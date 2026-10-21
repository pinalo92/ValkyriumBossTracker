"""Tapa Qt sobre el engranaje de Ajustes del DPS meter (A2Tools)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from ..sources.a2tools_companion import (
    GEAR_COVER_COLOR,
    GEAR_COVER_H,
    GEAR_COVER_W,
    gear_cover_screen_pos,
)


class SettingsGearCover(QWidget):
    """Cuadradito siempre encima que tapa .settingsBtn del meter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFixedSize(GEAR_COVER_W, GEAR_COVER_H)
        self.setStyleSheet(f"background:{GEAR_COVER_COLOR}; border:none;")

    def tick(self) -> None:
        pos = gear_cover_screen_pos()
        if not pos:
            if self.isVisible():
                self.hide()
            return
        x, y = pos
        self.move(x, y)
        if not self.isVisible():
            self.show()
        else:
            self.raise_()
