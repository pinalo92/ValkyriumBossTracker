"""Toast propio Valkyrium (no usa notificaciones de Windows)."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .brand import BG_CARD, BLUE_TP, BORDER_GLOW, PURPLE, TEXT, CSS_DISPLAY, CSS_UI


class Toast(QWidget):
    _active: list["Toast"] = []

    def __init__(self, title: str, body: str, ms: int = 2400, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet(
            f"QWidget{{background:{BG_CARD};border:1px solid {BORDER_GLOW};"
            f"border-radius:10px;}}"
            f"QLabel#title{{color:{PURPLE};font-family:{CSS_DISPLAY};"
            f"font-size:12px;font-weight:700;}}"
            f"QLabel#body{{color:{TEXT};font-family:{CSS_UI};font-size:13px;}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("title")
        b = QLabel(body)
        b.setObjectName("body")
        b.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(b)
        self.adjustSize()
        self.setFixedWidth(max(220, self.sizeHint().width()))
        self._place()
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(0.96)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()
        QTimer.singleShot(ms, self._dismiss)
        Toast._active.append(self)
        self._reflow()

    def _place(self):
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else self.rect()
        margin = 16
        x = geo.right() - self.width() - margin
        y = geo.bottom() - self.height() - margin
        self.move(x, y)

    @classmethod
    def _reflow(cls):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        margin = 16
        gap = 8
        y = geo.bottom() - margin
        for toast in reversed(cls._active):
            if toast is None:
                continue
            y -= toast.height()
            toast.move(geo.right() - toast.width() - margin, y)
            y -= gap

    def _dismiss(self):
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(220)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self._cleanup)
        anim.start()
        self._out = anim  # keep ref

    def _cleanup(self):
        if self in Toast._active:
            Toast._active.remove(self)
        self.close()
        self.deleteLater()
        Toast._reflow()


def show_toast(title: str, body: str, ms: int = 2400) -> None:
    Toast(title, body, ms=ms).show()
