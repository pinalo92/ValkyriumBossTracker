"""Panel izquierdo: a dónde ir ahora según tiempo + rotación (ruta)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..catalog import bosses, teleports
from ..engine import (
    build_route,
    format_alive_dead,
    format_countdown,
    format_tp_number,
    refresh_observation,
)
from ..models import AppSettings, BossObservation
from ..storage import load_tp_numbers


class NextTargetPanel(QFrame):
    """Bloque grande a la izquierda: boss prioritario + siguientes de la rotación."""

    boss_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nextPanel")
        self.setMinimumWidth(220)
        self.setMaximumWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        self.head = QLabel("IR AHORA")
        self.head.setObjectName("nextHead")
        self.head.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.estado = QLabel("—")
        self.estado.setObjectName("nextEstado")
        self.estado.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.nombre = QLabel("Sin objetivo")
        self.nombre.setObjectName("nextNombre")
        self.nombre.setWordWrap(True)
        self.nombre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nombre.setCursor(Qt.CursorShape.PointingHandCursor)

        self.tp = QLabel("TP —")
        self.tp.setObjectName("nextTp")
        self.tp.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.timer = QLabel("")
        self.timer.setObjectName("nextTimer")
        self.timer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.razon = QLabel("Según tiempo y rotación del feed")
        self.razon.setObjectName("nextRazon")
        self.razon.setWordWrap(True)
        self.razon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.despues = QLabel("")
        self.despues.setObjectName("nextDespues")
        self.despues.setWordWrap(True)
        self.despues.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for w in (
            self.head,
            self.estado,
            self.nombre,
            self.tp,
            self.timer,
            self.razon,
            self.despues,
        ):
            lay.addWidget(w)
        lay.addStretch(1)

        self._boss_id = ""
        self.nombre.mousePressEvent = self._click_name  # type: ignore[method-assign]

    def _click_name(self, event):
        if self._boss_id and event.button() == Qt.MouseButton.LeftButton:
            self.boss_clicked.emit(self._boss_id)

    def update_from_route(
        self,
        settings: AppSettings,
        observations: dict[str, BossObservation],
    ):
        catalog = bosses()
        tps = teleports(load_tp_numbers())
        route = build_route(settings, observations, max_stops=5)
        if not route:
            self._boss_id = ""
            self.estado.setText("—")
            self.nombre.setText("Sin objetivo")
            self.tp.setText("TP —")
            self.timer.setText("")
            self.razon.setText("Espera sync A2Tools o marca VIVO/MUERTO")
            self.despues.setText("")
            return

        first = route[0]
        boss = catalog[first.boss_id]
        tp = tps.get(first.nearest_tp_id)
        obs = refresh_observation(boss, observations.get(boss.id), settings)
        st = format_alive_dead(obs)
        self._boss_id = boss.id

        colors = {
            "VIVO": "#3fb950",
            "MUERTO": "#ff7b72",
            "VENTANA": "#ffb454",
            "¿?": "#8b949e",
        }
        self.estado.setText(st)
        self.estado.setStyleSheet(f"color:{colors.get(st, '#e7ecf3')};")
        self.nombre.setText(boss.name_es)
        self.tp.setText(f"TP {format_tp_number(tp)}")
        self.timer.setText(format_countdown(obs))
        why = first.reason or "mejor por tiempo + viaje"
        self.razon.setText(why)

        lines = ["<b>Después</b>"]
        for stop in route[1:4]:
            b = catalog.get(stop.boss_id)
            if not b:
                continue
            t = tps.get(stop.nearest_tp_id)
            o = refresh_observation(b, observations.get(b.id), settings)
            lines.append(
                f"{stop.order}. {b.name_es}<br>"
                f"&nbsp;&nbsp;<span style='color:#8ee9ff'>{format_tp_number(t)}</span> · "
                f"{format_alive_dead(o)} · {format_countdown(o)}"
            )
        self.despues.setText("<br>".join(lines) if len(lines) > 1 else "")


class NextTargetCompact(QFrame):
    """Versión pequeña para el overlay (izquierda de los pins)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nextCompact")
        self.setFixedWidth(150)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(2)
        self.lbl = QLabel("IR →\n—")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setWordWrap(True)
        f = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        self.lbl.setFont(f)
        lay.addWidget(self.lbl)

    def set_target(
        self,
        settings: AppSettings,
        observations: dict[str, BossObservation],
    ):
        catalog = bosses()
        tps = teleports(load_tp_numbers())
        route = build_route(settings, observations, max_stops=1)
        self.lbl.setTextFormat(Qt.TextFormat.RichText)
        if not route:
            self.lbl.setText("IR →<br>—")
            return
        boss = catalog[route[0].boss_id]
        tp = tps.get(route[0].nearest_tp_id)
        obs = refresh_observation(boss, observations.get(boss.id), settings)
        name = boss.name_es
        if len(name) > 18:
            name = name[:17] + "…"
        self.lbl.setText(
            f"<b>IR →</b><br>{name}<br>"
            f"<span style='color:#8ee9ff;font-size:16px;font-family:Cascadia Mono'>"
            f"TP {format_tp_number(tp)}</span><br>"
            f"{format_alive_dead(obs)} · {format_countdown(obs)}"
        )
