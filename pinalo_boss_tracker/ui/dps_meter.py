"""Overlay del medidor de DPS. El logo de la guild se carga cuando exista el archivo."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QMenu, QWidget

from ..dps.capture import NpcapCapture
from ..dps.session import CombatSession, MeterView, format_clock, format_number
from ..paths import app_dir
from ..resources import package_data_dir
from .brand import (
    BG,
    BG_CARD,
    BLUE_DEEP,
    BLUE_P,
    BLUE_TP,
    BORDER_GLOW,
    PURPLE,
    TEXT,
    TEXT_DIM,
    TEXT_MUTED,
    font_display,
    font_ui,
)

_W = 348
_LOGO_NAMES = ("guild_logo.png", "guild_logo.jpg", "guild_logo.webp", "logo_guild.png")


def find_guild_logo() -> Path | None:
    """Cuando pases el logo, déjalo como guild_logo.png en data/ o junto a los datos de la app."""
    roots = (
        package_data_dir(),
        app_dir(),
        Path.home() / "AppData" / "Local" / "Valkyrium",
    )
    for root in roots:
        for name in _LOGO_NAMES:
            path = root / name
            if path.is_file():
                return path
    return None


class DpsMeterWindow(QWidget):
    closed = Signal()
    moved = Signal(int, int)

    def __init__(self, session: CombatSession | None = None, parent=None):
        super().__init__(parent)
        self.session = session or CombatSession()
        self._capture = NpcapCapture(self.session)
        self._view = self.session.snapshot()
        self._logo = self._load_logo()
        self._drag: QPoint | None = None
        self._drag_origin = QPoint()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Valkyrium DPS")
        self.setFixedWidth(_W)
        self._fit()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(200)

    def start_listening(self) -> None:
        self._capture.start()

    def stop_listening(self) -> None:
        self._capture.stop()
        self._timer.stop()

    def _load_logo(self) -> QPixmap | None:
        path = find_guild_logo()
        if path is None:
            return None
        pm = QPixmap(str(path))
        if pm.isNull():
            return None
        return pm

    def _tick(self) -> None:
        view = self.session.snapshot()
        if _view_key(view) != _view_key(self._view):
            self._view = view
            self._fit()
            self.update()
        else:
            self._view = view
            self.update()

    def _fit(self) -> None:
        rows = max(1, len(self._view.rows))
        height = 118 + rows * 34 + 28
        self.setFixedHeight(height)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        card = QPainterPath()
        card.addRoundedRect(rect, 16, 16)
        p.fillPath(card, QColor(BG))
        p.setPen(QPen(QColor(BORDER_GLOW), 1.4))
        p.drawPath(card)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PURPLE))
        p.drawRoundedRect(18, 0, 92, 3, 1, 1)

        self._paint_logo(p, 16, 16, 46)
        p.setPen(QColor(TEXT))
        p.setFont(font_display(15, QFont.Weight.Bold))
        p.drawText(72, 18, 250, 22, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "VALKYRIUM")
        p.setPen(QColor(BLUE_TP))
        p.setFont(font_ui(9, QFont.Weight.DemiBold))
        p.drawText(72, 40, 250, 16, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "App oficial de Valkyrium")

        view = self._view
        headline = "En combate" if view.fighting else "Esperando combate"
        clock = format_clock(view.elapsed_s) if view.fighting else "--:--"
        p.setPen(QColor(PURPLE))
        p.setFont(font_ui(11, QFont.Weight.DemiBold))
        p.drawText(16, 72, 180, 18, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, headline)
        p.setPen(QColor(TEXT_MUTED))
        p.setFont(font_ui(11))
        p.drawText(180, 72, 152, 18, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, clock)

        y = 98
        if not view.rows:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font_ui(11))
            p.drawText(16, y, _W - 32, 36, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "El grupo aparece aquí al pegar.")
            y += 40
        else:
            top = view.rows[0].dps or 1
            for row in view.rows:
                self._paint_row(p, row, y, top)
                y += 34

        p.setPen(QColor(TEXT_DIM))
        p.setFont(font_ui(9))
        status = view.status
        if view.fighting:
            status = f"{status}  ·  {format_number(view.your_dps)} DPS"
        p.drawText(16, self.height() - 26, _W - 32, 16, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status)
        p.end()

    def _paint_logo(self, p: QPainter, x: int, y: int, size: int) -> None:
        p.save()
        ring = QPainterPath()
        ring.addEllipse(x, y, size, size)
        glow = QRadialGradient(x + size / 2, y + size / 2, size / 2)
        glow.setColorAt(0.0, QColor("#123044"))
        glow.setColorAt(1.0, QColor(BG))
        p.fillPath(ring, glow)
        if self._logo is not None:
            clip = QPainterPath()
            clip.addEllipse(x + 2, y + 2, size - 4, size - 4)
            p.setClipPath(clip)
            p.drawPixmap(x + 2, y + 2, size - 4, size - 4, self._logo)
            p.setClipping(False)
        else:
            p.setPen(QColor(BLUE_P))
            p.setFont(font_display(18, QFont.Weight.Bold))
            p.drawText(x, y, size, size, Qt.AlignmentFlag.AlignCenter, "V")
        p.setPen(QPen(QColor(PURPLE), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(x, y, size, size)
        p.restore()

    def _paint_row(self, p: QPainter, row, y: int, top_dps: float) -> None:
        bar_w = _W - 32
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BG_CARD))
        p.drawRoundedRect(16, y, bar_w, 28, 7, 7)
        fill = max(8, int(bar_w * (row.dps / top_dps)))
        color = QColor(BLUE_DEEP) if row.you else QColor(BORDER_GLOW)
        p.setBrush(color)
        p.drawRoundedRect(16, y, fill, 28, 7, 7)
        p.setPen(QColor(TEXT))
        p.setFont(font_ui(11, QFont.Weight.DemiBold))
        name = ("Tú  " if row.you else "") + row.name
        p.drawText(24, y, 150, 28, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        p.setFont(font_ui(10))
        p.drawText(160, y, bar_w - 28, 28, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{format_number(row.dps)}   {row.pct:.0f}%")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint()
            self._drag_origin = self.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.addAction("Reiniciar combate", self.session.reset_fight)
            menu.addAction("Ocultar", self.hide)
            menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self._drag is None:
            return
        delta = event.globalPosition().toPoint() - self._drag
        self.move(self._drag_origin + delta)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag is not None:
            self._drag = None
            self.moved.emit(self.x(), self.y())

    def wheelEvent(self, event) -> None:
        step = 0.05 if event.angleDelta().y() > 0 else -0.05
        opacity = max(0.45, min(1.0, self.windowOpacity() + step))
        self.setWindowOpacity(opacity)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.x() == 0 and self.y() == 0:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.move(area.right() - self.width() - 28, area.top() + 72)

    def closeEvent(self, event) -> None:
        self.stop_listening()
        self.closed.emit()
        super().closeEvent(event)


def _view_key(view: MeterView) -> tuple:
    return (
        view.fighting,
        view.status,
        tuple((r.name, r.damage, r.you, int(r.dps)) for r in view.rows),
    )
