"""Pins estilo A2Tools Event Timers: icono + Activo/HP/timer + #TP debajo."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .boss_faces import draw_circular_face, face_pixmap
from .brand import (
    BLUE_TP,
    PURPLE,
    TEXT,
    TEXT_MUTED,
    font_display,
    font_mono,
    font_ui,
    qcolor,
)

from ..catalog import bosses
from ..engine import (
    build_route,
    format_alive_dead,
    format_countdown,
    format_tp_number,
    minutes_until,
    refresh_observation,
    tp_for,
)
from ..models import AppSettings, BossDef, BossKind, BossObservation, Reliability, utcnow
from ..storage import load_tp_numbers

from ..resources import package_data_dir

A2_SETTINGS = Path.home() / "AppData" / "Roaming" / "com.a2tools.dps-meter" / "settings.json"
FIELD_MAP = package_data_dir() / "a2tools_field_ids.json"


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def a2tools_pinned_field_ids() -> list[str]:
    """IDs field:* que el usuario tiene como widgets en A2Tools."""
    try:
        data = json.loads(A2_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[str] = []
    for key in data:
        m = re.match(r"dpsMeter\.pluginWidget\.event-timers\.field-(\d+)$", str(key))
        if m:
            out.append(m.group(1))
    return out


def field_id_to_local(field_id: str) -> Optional[str]:
    try:
        fmap = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    meta = fmap.get(str(field_id)) or {}
    en = meta.get("en") or ""
    es = meta.get("es") or ""
    for bid, b in bosses().items():
        if _normalize(b.name) == _normalize(en) or _normalize(b.name_es) == _normalize(es):
            return bid
    return None


def is_live_combat(obs: BossObservation, now=None) -> bool:
    """True si el feed manda HP%: alguien con meter está peleando ahí."""
    if obs.hp is None:
        return False
    return format_alive_dead(obs, now) == "VIVO"


def select_pin_bosses(
    settings: AppSettings,
    observations: dict[str, BossObservation],
    limit: int = 12,
) -> list[tuple[BossDef, BossObservation]]:
    """Solo bosses vivos o que faltan ≤ alert_lead_minutes (5) para salir.

    Orden: en combate (HP live) → favoritos → pronto a salir → ruta.
    Entre combates, menor HP primero (pelea más avanzada / más caliente).
    """
    catalog = bosses()
    now = utcnow()
    lead = float(settings.alert_lead_minutes or 5)

    def faction_ok(boss: BossDef) -> bool:
        # Field + abismo programado (incl. Velador Kaira)
        if boss.kind == BossKind.SCHEDULED:
            return True
        if boss.kind != BossKind.FIELD:
            return False
        if settings.faction == "elyos" and boss.faction == "asmodian":
            return False
        if settings.faction == "asmodian" and boss.faction == "elyos":
            return False
        return True

    def ready_mins(obs: BossObservation) -> float:
        st = format_alive_dead(obs, now)
        if st == "VIVO":
            return 0.0
        if st == "VENTANA":
            return 0.0
        if obs.predicted_ready_at:
            m = minutes_until(obs.predicted_ready_at, now)
            if m is not None:
                return max(0.0, m)
        return 9999.0

    def soon_enough(obs: BossObservation) -> bool:
        """Vivo, en ventana, o sale en ≤ lead minutos."""
        return ready_mins(obs) <= lead

    # Orden de ruta solo para desempate
    route = build_route(settings, observations, now=now, max_stops=20)
    route_pos = {s.boss_id: i for i, s in enumerate(route)}

    favs = set(settings.favorite_boss_ids or [])
    # combat_rank, hp_sort, fav_rank, ready_mins, route_pos
    rows: list[tuple[BossDef, BossObservation, int, float, int, float, int]] = []
    for bid, boss in catalog.items():
        if not faction_ok(boss):
            continue
        if bid in (settings.excluded_boss_ids or []):
            continue
        obs = refresh_observation(boss, observations.get(bid), settings, now)
        is_fav = bid in favs
        in_combat = is_live_combat(obs, now)
        if not is_fav and not soon_enough(obs) and not in_combat:
            continue
        rm = ready_mins(obs)
        pos = route_pos.get(bid, 1000)
        try:
            hp_sort = float(obs.hp) if in_combat else 999.0
        except (TypeError, ValueError):
            hp_sort = 999.0
        rows.append(
            (
                boss,
                obs,
                0 if in_combat else 1,
                hp_sort,
                0 if is_fav else 1,
                rm,
                pos,
            )
        )

    rows.sort(key=lambda t: (t[2], t[3], t[4], t[5], t[6], t[0].name_es))
    return [(b, o) for b, o, *_ in rows[:limit]]


def _hp_color(hp: float | int) -> QColor:
    """Colores del anillo HP de A2Tools Event Timers."""
    h = float(hp)
    if h > 50:
        return QColor("#5fe08a")
    if h > 20:
        return QColor("#ffd54a")
    return QColor("#ff5a4f")


def _draw_hp_arc(
    p: QPainter,
    arc: QRectF,
    hp: float,
    color: QColor,
    width: float = 3.0,
) -> None:
    """Arco de HP con punta luminosa (efecto flujo)."""
    hp = max(0.0, min(100.0, float(hp)))
    span_deg = -360.0 * hp / 100.0
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(arc, int(90 * 16), int(span_deg * 16))
    if hp < 0.4:
        return
    # Punta del arco (fluye con el %)
    end_deg = 90.0 + span_deg
    rad = math.radians(end_deg)
    cx = arc.center().x()
    cy = arc.center().y()
    rx = arc.width() / 2.0
    ry = arc.height() / 2.0
    tip_x = cx + rx * math.cos(rad)
    tip_y = cy - ry * math.sin(rad)
    glow = QColor(color)
    glow.setAlpha(210)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QRectF(tip_x - 2.4, tip_y - 2.4, 4.8, 4.8))
    p.setBrush(QColor(255, 255, 255, 200))
    p.drawEllipse(QRectF(tip_x - 1.15, tip_y - 1.15, 2.3, 2.3))


ABYSS_PURPLE = qcolor(PURPLE)  # Valkyrium / abismo
ABYSS_GREEN = QColor("#5fe08a")


def _ring_color(obs: BossObservation, boss: Optional[BossDef] = None) -> QColor:
    from ..engine import is_abyss_boss

    st = format_alive_dead(obs)
    abyss = bool(boss and is_abyss_boss(boss))
    if obs.hp is not None and st == "VIVO":
        return _hp_color(int(obs.hp))
    if st == "VIVO":
        return ABYSS_GREEN if abyss else QColor("#5fe08a")
    if st == "VENTANA":
        return QColor("#ffd54a") if not abyss else ABYSS_PURPLE
    if st == "MUERTO":
        return QColor("#9aa4b2") if not abyss else QColor("#8a6bb8")
    return ABYSS_PURPLE if abyss else QColor("#ff7a6b")


def _status_lines(obs: BossObservation) -> tuple[str, str, bool]:
    """(time, sub, derrotado?) — mismo orden que widget A2Tools."""
    st = format_alive_dead(obs)
    if st == "VIVO":
        # Solo % real del live; nunca inventar 100.
        if obs.hp is not None:
            try:
                pct = max(0, min(100, int(round(float(obs.hp)))))
            except (TypeError, ValueError):
                pct = int(obs.hp)
            return "Combate", f"{pct}%", False
        return "Activo", "", False
    if st == "MUERTO":
        mins = minutes_until(obs.predicted_ready_at) if obs.predicted_ready_at else None
        if mins is not None and 0 <= mins < 60:
            total = int(mins * 60)
            timer = f"{total // 60}:{total % 60:02d}"
        else:
            cd = format_countdown(obs)
            timer = cd.split(" ")[0] if cd and cd != "—" else ""
        return "Derrotado", timer, True
    if st == "VENTANA":
        # Horario de spawn ≠ confirmado vivo (p.ej. Kaira)
        return "Ventana", "", False
    return "¿?", "", False


def _initials(name: str) -> str:
    words = [w for w in re.split(r"[\s·:,\-]+", name or "") if w]
    if not words:
        return "?"
    if len(words) > 1:
        return (words[0][0] + words[-1][0]).upper()
    return words[0][:2].upper()


def _draw_outlined_text(
    p: QPainter,
    rect: QRectF,
    text: str,
    font: QFont,
    fill: QColor,
    outline: float = 2.6,
    strike: bool = False,
    align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
):
    """Texto con borde negro; opcional tachado (derrotado)."""
    p.setFont(font)
    path = QPainterPath()
    fm_h = p.fontMetrics().height()
    tw = p.fontMetrics().horizontalAdvance(text)
    x = rect.x()
    y = rect.y() + (rect.height() + fm_h) / 2 - p.fontMetrics().descent()
    if align & Qt.AlignmentFlag.AlignHCenter:
        x = rect.center().x() - tw / 2
    path.addText(x, y, font, text)
    p.setPen(
        QPen(
            QColor(0, 0, 0, 240),
            outline,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fill)
    p.drawPath(path)
    if strike and text:
        mid_y = rect.center().y()
        p.setPen(QPen(QColor(255, 90, 80, 230), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(
            int(rect.center().x() - tw / 2 - 1),
            int(mid_y),
            int(rect.center().x() + tw / 2 + 1),
            int(mid_y),
        )


def _draw_boss_skull(p: QPainter, cx: float, cy: float, scale: float = 1.0):
    """Calavera con cuernos, estilo icono field boss."""
    s = scale
    # cuernos
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#f2f4f8"))
    left = QPainterPath()
    left.moveTo(cx - 6 * s, cy - 8 * s)
    left.cubicTo(cx - 18 * s, cy - 22 * s, cx - 16 * s, cy - 4 * s, cx - 9 * s, cy - 2 * s)
    left.closeSubpath()
    right = QPainterPath()
    right.moveTo(cx + 6 * s, cy - 8 * s)
    right.cubicTo(cx + 18 * s, cy - 22 * s, cx + 16 * s, cy - 4 * s, cx + 9 * s, cy - 2 * s)
    right.closeSubpath()
    p.drawPath(left)
    p.drawPath(right)
    # cráneo
    p.drawEllipse(QRectF(cx - 11 * s, cy - 12 * s, 22 * s, 20 * s))
    # ojos
    p.setBrush(QColor("#12151c"))
    p.drawEllipse(QRectF(cx - 7 * s, cy - 6 * s, 5 * s, 6 * s))
    p.drawEllipse(QRectF(cx + 2 * s, cy - 6 * s, 5 * s, 6 * s))
    # mandíbula
    p.setBrush(QColor("#f2f4f8"))
    p.drawRoundedRect(QRectF(cx - 7 * s, cy + 4 * s, 14 * s, 7 * s), 2 * s, 2 * s)
    p.setBrush(QColor("#12151c"))
    for i in range(3):
        p.drawRect(QRectF(cx - 5 * s + i * 4 * s, cy + 5 * s, 1.5 * s, 4 * s))


class BossPinWidget(QWidget):
    """Pin visual clonado del widget A2Tools Event Timers (badge + time + sub + name + TP)."""

    clicked = Signal(str)
    mark_dead_requested = Signal(str)
    favorite_toggled = Signal(str)

    def __init__(
        self,
        boss: BossDef,
        obs: BossObservation,
        tp_label: str,
        tp_name: str = "",
        parent=None,
        scale: float = 1.0,
    ):
        super().__init__(parent)
        self.boss_id = boss.id
        self._boss = boss
        self._obs = obs
        self._tp = tp_label
        self._tp_name = tp_name
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        # HP mostrado (interpolado); -1 = sin anillo
        self._display_hp = -1.0
        if (
            format_alive_dead(obs) == "VIVO"
            and obs.hp is not None
        ):
            try:
                self._display_hp = max(0.0, min(100.0, float(obs.hp)))
            except (TypeError, ValueError):
                self._display_hp = -1.0
        self._hp_anim = QPropertyAnimation(self, b"displayHp", self)
        self._hp_anim.setDuration(320)
        self._hp_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Celda un poco más alta: hueco entre estado / nombre / TP
        self._apply_scale_size()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tip()

    def _get_display_hp(self) -> float:
        return self._display_hp

    def _set_display_hp(self, value: float):
        self._display_hp = float(value)
        self.update()

    displayHp = Property(float, _get_display_hp, _set_display_hp)

    def _apply_scale_size(self):
        s = self._scale
        self.setFixedSize(max(40, int(round(80 * s))), max(74, int(round(148 * s))))

    def set_scale(self, scale: float):
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self._apply_scale_size()
        self.update()

    def _tip(self):
        extra = f"\n{self._tp_name}" if self._tp_name else ""
        shown = self._display_hp if self._display_hp >= 0 else self._obs.hp
        hp = f"\nHP {int(round(float(shown)))}%" if shown is not None and float(shown) >= 0 else ""
        combat = ""
        if is_live_combat(self._obs) or (
            self._display_hp >= 0 and format_alive_dead(self._obs) == "VIVO"
        ):
            combat = "\nEn combate (HP live) — gente con meter aquí"
        self.setToolTip(
            f"{self._boss.name_es}\n{self._tp}{extra}{hp}{combat}\n"
            "Clic: copiar #TP · Clic der.: marcar muerto\n"
            "Rueda: opacidad · Ctrl+rueda: escala"
        )

    def _animate_hp_to(self, target: Optional[float]):
        """Interpola el anillo hacia el nuevo % (o apaga si no hay HP)."""
        if target is None:
            self._hp_anim.stop()
            self._display_hp = -1.0
            self.update()
            return
        target = max(0.0, min(100.0, float(target)))
        if self._display_hp < 0:
            self._display_hp = target
            self.update()
            return
        if abs(self._display_hp - target) < 0.15:
            self._display_hp = target
            self.update()
            return
        self._hp_anim.stop()
        self._hp_anim.setStartValue(self._display_hp)
        self._hp_anim.setEndValue(target)
        # Combates rápidos: un poco más ágil si el salto es grande
        jump = abs(self._display_hp - target)
        self._hp_anim.setDuration(220 if jump >= 12 else 320)
        self._hp_anim.start()

    def update_data(
        self,
        boss: BossDef,
        obs: BossObservation,
        tp_label: str,
        tp_name: str = "",
    ):
        self._boss = boss
        self._obs = obs
        self._tp = tp_label
        self._tp_name = tp_name
        self.boss_id = boss.id
        st = format_alive_dead(obs)
        if st == "VIVO" and obs.hp is not None:
            try:
                self._animate_hp_to(float(obs.hp))
            except (TypeError, ValueError):
                self._animate_hp_to(None)
        else:
            self._animate_hp_to(None)
        self._tip()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.boss_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self.mark_dead_requested.emit(self.boss_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_copy = menu.addAction("Copiar WB (chat)")
        act_dead = menu.addAction("Marcar muerto")
        act_fav = menu.addAction("★ Favorito (siempre visible)")
        chosen = menu.exec(event.globalPos())
        if chosen == act_copy:
            self.clicked.emit(self.boss_id)
        elif chosen == act_dead:
            self.mark_dead_requested.emit(self.boss_id)
        elif chosen == act_fav:
            self.favorite_toggled.emit(self.boss_id)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        s = self._scale
        if s != 1.0:
            p.scale(s, s)

        st = format_alive_dead(self._obs)
        alive = st == "VIVO"
        hp_f = self._display_hp
        has_hp = alive and hp_f >= 0
        main, sub, dead = _status_lines(self._obs)
        if has_hp:
            main = "Combate"
            sub = f"{int(round(hp_f))}%"
        from ..engine import is_abyss_boss

        abyss = is_abyss_boss(self._boss)
        ring = _hp_color(hp_f) if has_hp else _ring_color(self._obs, self._boss)
        # Coordenadas lógicas (80×148); el painter ya aplica scale
        cx, cy, r = 40.0, 28.0, 21.0  # badge 42px

        # Resplandor si hay HP live (= pelea activa / “a dónde va la gente”)
        if has_hp:
            glow = QColor(_hp_color(hp_f))
            for expand, alpha in ((11.0, 40), (7.5, 70), (5.0, 110)):
                c = QColor(glow)
                c.setAlpha(alpha)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(
                    QRectF(
                        cx - r - expand,
                        cy - r - expand,
                        (r + expand) * 2,
                        (r + expand) * 2,
                    )
                )

        # Sombra bajo el badge (como box-shadow A2Tools)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawEllipse(QRectF(cx - r + 1, cy - r + 3, r * 2, r * 2))

        # Badge: radial-gradient(circle at 35% 30%, …)
        grad = QRadialGradient(cx - r * 0.3, cy - r * 0.35, r * 1.35)
        grad.setColorAt(0.0, QColor(255, 255, 255, 56))
        grad.setColorAt(0.55, QColor(28, 34, 48, 235))
        grad.setColorAt(1.0, QColor(12, 16, 26, 235))
        p.setBrush(grad)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Anillo: field = verde/coral; abismo = morado + verde (HP animado)
        arc = QRectF(cx - r - 3, cy - r - 3, (r + 3) * 2, (r + 3) * 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if abyss:
            # Base morada (marca abismo, como .pin.boss A2Tools)
            p.setPen(QPen(ABYSS_PURPLE, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawEllipse(arc)
            if has_hp:
                _draw_hp_arc(p, arc, hp_f, _hp_color(hp_f), width=3.0)
            elif alive or st == "VENTANA":
                # Segundo tono verde (vivo / ventana)
                inner = QRectF(cx - r - 0.5, cy - r - 0.5, (r + 0.5) * 2, (r + 0.5) * 2)
                p.setPen(
                    QPen(
                        ABYSS_GREEN if alive else QColor("#ffd54a"),
                        2.2,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                p.drawEllipse(inner)
        elif has_hp:
            p.setPen(QPen(QColor(255, 255, 255, 46), 3.0))
            p.drawEllipse(arc)
            _draw_hp_arc(p, arc, hp_f, ring, width=3.0)
        else:
            pen = QPen(ring, 2.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawEllipse(QRectF(cx - r - 1, cy - r - 1, (r + 1) * 2, (r + 1) * 2))

        # Cara del boss (retrato) o fallback calavera / iniciales
        face = face_pixmap(self._boss.id)
        face_r = r - 2.5
        if face is not None:
            draw_circular_face(p, face, cx, cy, face_r)
            if dead:
                # velo oscuro si derrotado
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(12, 16, 26, 140))
                p.drawEllipse(QRectF(cx - face_r, cy - face_r, face_r * 2, face_r * 2))
        elif alive or st == "VENTANA":
            _draw_boss_skull(p, cx, cy + 1, 0.85)
        else:
            glyph = _initials(self._boss.name_es)
            _draw_outlined_text(
                p,
                QRectF(cx - r, cy - 8, r * 2, 18),
                glyph,
                font_display(11, QFont.Weight.Bold),
                qcolor(TEXT),
                outline=2.4,
            )

        y = 54.0
        gap_after_status = 5.0  # hueco Activo/Combate → nombre
        gap_before_tp = 5.0     # hueco nombre → #TP

        # .time
        if dead:
            time_color = QColor("#ff8a80")
        elif has_hp:
            time_color = ring
        elif alive:
            time_color = QColor("#5fe08a")
        elif st == "VENTANA":
            time_color = QColor("#ffd54a")
        else:
            time_color = QColor("#ffffff")

        logical_w = 80.0
        if main:
            _draw_outlined_text(
                p,
                QRectF(1, y, logical_w - 2, 14),
                main,
                font_ui(9, QFont.Weight.DemiBold),
                time_color,
                outline=2.2,
                strike=dead,
            )
            y += 14

        # .sub (HP% o timer) — pegado al estado, no al nombre
        if sub:
            sub_color = (
                QColor("#ff8a80")
                if dead
                else (ring if has_hp else QColor("#ffe08a"))
            )
            _draw_outlined_text(
                p,
                QRectF(1, y, logical_w - 2, 13),
                sub,
                font_mono(9, QFont.Weight.Bold),
                sub_color,
                outline=2.2,
            )
            y += 13

        y += gap_after_status

        # .name (hasta 2 líneas, max ~78px)
        name = self._boss.name_es
        name_font = font_ui(8, QFont.Weight.Medium)
        p.setFont(name_font)
        max_w = logical_w - 4
        words = name.split()
        line1, line2 = name, ""
        if p.fontMetrics().horizontalAdvance(name) > max_w and len(words) >= 2:
            mid = max(1, len(words) // 2)
            line1 = " ".join(words[:mid])
            line2 = " ".join(words[mid:])
            if p.fontMetrics().horizontalAdvance(line1) > max_w:
                while line1 and p.fontMetrics().horizontalAdvance(line1 + "…") > max_w:
                    line1 = line1[:-1]
                line1 = line1 + "…"
            if p.fontMetrics().horizontalAdvance(line2) > max_w:
                while line2 and p.fontMetrics().horizontalAdvance(line2 + "…") > max_w:
                    line2 = line2[:-1]
                line2 = line2 + "…"
        elif p.fontMetrics().horizontalAdvance(name) > max_w:
            while name and p.fontMetrics().horizontalAdvance(name + "…") > max_w:
                name = name[:-1]
            line1 = name + "…"

        # Nombre siempre legible (el tachado solo en "Derrotado")
        name_color = qcolor(TEXT_MUTED) if dead else qcolor(TEXT)
        _draw_outlined_text(
            p,
            QRectF(2, y, logical_w - 4, 12),
            line1,
            name_font,
            name_color,
            outline=2.2,
            strike=False,
        )
        y += 12
        if line2:
            _draw_outlined_text(
                p,
                QRectF(2, y, logical_w - 4, 12),
                line2,
                name_font,
                name_color,
                outline=2.2,
                strike=False,
            )
            y += 12

        y += gap_before_tp

        # .tp
        tp_txt = self._tp if str(self._tp).startswith("#") else f"#{self._tp}".replace("##", "#")
        if tp_txt in ("#—", "#", "#None"):
            tp_txt = "—"
        _draw_outlined_text(
            p,
            QRectF(0, y, logical_w, 14),
            tp_txt,
            font_mono(10, QFont.Weight.Bold),
            qcolor(BLUE_TP),
            outline=2.2,
        )


class PinStrip(QWidget):
    boss_clicked = Signal(str)
    boss_mark_dead = Signal(str)
    boss_favorite = Signal(str)

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self._layout = QHBoxLayout(self)
        # Padding-top como A2Tools (hueco del glow del badge)
        self._apply_layout_metrics()
        self._pins: dict[str, BossPinWidget] = {}
        self.setFixedHeight(max(90, int(round(158 * self._scale))))

    def _apply_layout_metrics(self):
        s = self._scale
        self._layout.setContentsMargins(
            max(2, int(round(4 * s))),
            # Extra top: hueco para el resplandor de bosses en combate
            max(6, int(round(14 * s))),
            max(2, int(round(4 * s))),
            max(1, int(round(2 * s))),
        )
        self._layout.setSpacing(max(1, int(round(2 * s))))

    def set_scale(self, scale: float):
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self._apply_layout_metrics()
        for pin in self._pins.values():
            pin.set_scale(self._scale)
        n = max(1, len(self._pins))
        self.setFixedWidth(max(40, int(round(4 + n * 82 * self._scale + 4))))
        self.setFixedHeight(max(90, int(round(158 * self._scale))))
        self.update()

    def paintEvent(self, event):
        # Sin caja de fondo: solo los pins (como A2Tools)
        super().paintEvent(event)

    def set_pins(self, items: list[tuple[BossDef, BossObservation]]):
        wanted = []
        overrides = load_tp_numbers()
        for boss, obs in items:
            tp = tp_for(boss, overrides)
            wanted.append(
                (boss, obs, format_tp_number(tp), tp.name if tp else "")
            )

        ids = {b.id for b, _, _, _ in wanted}
        for bid in list(self._pins):
            if bid not in ids:
                w = self._pins.pop(bid)
                self._layout.removeWidget(w)
                w.deleteLater()

        # Reordenar: quitar del layout y volver a añadir
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w and w not in self._pins.values():
                w.setParent(None)

        for boss, obs, tp_lbl, tp_name in wanted:
            pin = self._pins.get(boss.id)
            if pin is None:
                pin = BossPinWidget(boss, obs, tp_lbl, tp_name, scale=self._scale)
                pin.clicked.connect(self.boss_clicked.emit)
                pin.mark_dead_requested.connect(self.boss_mark_dead.emit)
                pin.favorite_toggled.connect(self.boss_favorite.emit)
                self._pins[boss.id] = pin
            else:
                pin.set_scale(self._scale)
                pin.update_data(boss, obs, tp_lbl, tp_name)
            self._layout.addWidget(pin)
        self._layout.addStretch(1)
        n = max(1, len(wanted))
        s = self._scale
        self.setFixedWidth(max(40, int(round(4 + n * 82 * s + 4))))
        self.setFixedHeight(max(90, int(round(158 * s))))

    def patch_pins(self, items: list[tuple[BossDef, BossObservation]]) -> bool:
        """Actualiza HP/estado sin reconstruir el layout. False si hay que set_pins."""
        overrides = load_tp_numbers()
        wanted: list[tuple[BossDef, BossObservation, str, str]] = []
        for boss, obs in items:
            tp = tp_for(boss, overrides)
            wanted.append(
                (boss, obs, format_tp_number(tp), tp.name if tp else "")
            )
        ids = [b.id for b, _, _, _ in wanted]
        # Orden actual de pins en el layout (sin stretch)
        current: list[str] = []
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if isinstance(w, BossPinWidget):
                current.append(w.boss_id)
        if ids != current:
            return False
        for boss, obs, tp_lbl, tp_name in wanted:
            pin = self._pins.get(boss.id)
            if pin is None:
                return False
            pin.update_data(boss, obs, tp_lbl, tp_name)
        return True


class BrandFooter(QWidget):
    """Marca bajo los pins: icono P + Valkyrium · by Pinalo."""

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self._logo = QPixmap()
        icon_path = package_data_dir() / "app_icon.png"
        if icon_path.is_file():
            self._logo = QPixmap(str(icon_path)).scaled(
                28,
                28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.setFixedHeight(max(22, int(round(36 * self._scale))))

    def set_scale(self, scale: float):
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self.setFixedHeight(max(22, int(round(36 * self._scale))))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        s = self._scale
        if s != 1.0:
            p.scale(s, s)
        w = 120.0  # ancho lógico mínimo de marca
        if self.width() / max(s, 0.01) > w:
            w = float(self.width()) / s
        icon_w = 0.0
        if not self._logo.isNull():
            icon_w = 28.0 + 6.0
            x = (w - icon_w - 90) / 2.0
            y = (36 - 28) / 2.0
            p.drawPixmap(int(max(0, x)), int(max(0, y)), self._logo)
            text_left = x + icon_w
            text_w = w - text_left
        else:
            text_left = 0.0
            text_w = w
        _draw_outlined_text(
            p,
            QRectF(text_left, 2, text_w, 16),
            "Valkyrium",
            font_display(10, QFont.Weight.Bold),
            qcolor(PURPLE),
            outline=2.0,
            align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        _draw_outlined_text(
            p,
            QRectF(text_left, 16, text_w, 14),
            "by Pinalo",
            font_ui(8, QFont.Weight.DemiBold),
            qcolor(BLUE_TP),
            outline=1.6,
            align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )


class KairaCountdownBar(QWidget):
    """Contador siempre visible: próxima ventana Velador Kaira."""

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self._text = "Kaira · —"
        self.setFixedHeight(max(18, int(round(22 * self._scale))))

    def set_scale(self, scale: float):
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self.setFixedHeight(max(18, int(round(22 * self._scale))))
        self.update()

    def set_text(self, text: str):
        if text != self._text:
            self._text = text
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        s = self._scale
        if s != 1.0:
            p.scale(s, s)
        w = float(self.width()) / max(s, 0.01)
        _draw_outlined_text(
            p,
            QRectF(0, 0, w, 22),
            self._text,
            font_mono(10, QFont.Weight.Bold),
            qcolor(PURPLE),
            outline=1.8,
            align=Qt.AlignmentFlag.AlignCenter,
        )


class PinsOverlay(QWidget):
    """Solo pins de bosses (como A2Tools) + TP. Sin textos de fuente/DPS ni paneles extra."""

    closed = Signal()
    appearance_changed = Signal(float, float)  # scale, opacity
    position_changed = Signal(int, int)  # x, y

    def __init__(self, scale: float = 1.0, opacity: float = 1.0):
        super().__init__(None)
        self.setWindowTitle("")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._drag: Optional[QPoint] = None
        self._moved = False
        self._scale = max(0.5, min(1.8, float(scale or 1.0)))
        self._opacity = max(0.30, min(1.0, float(opacity or 1.0)))
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.kaira = KairaCountdownBar(scale=self._scale)
        self.strip = PinStrip(scale=self._scale)
        self.brand = BrandFooter(scale=self._scale)
        col.addWidget(self.kaira, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(self.strip, 0, Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.brand, 0, Qt.AlignmentFlag.AlignHCenter)
        self.setWindowOpacity(self._opacity)
        self.resize(520, 210)

    def appearance(self) -> tuple[float, float]:
        return self._scale, self._opacity

    def _relayout(self):
        w = max(120, self.strip.width(), 160)
        self.kaira.setFixedWidth(w)
        self.brand.setFixedWidth(w)
        h = self.kaira.height() + self.strip.height() + self.brand.height()
        self.resize(w, h)
        self.adjustSize()

    def set_appearance(self, scale: float | None = None, opacity: float | None = None):
        if scale is not None:
            self._scale = max(0.5, min(1.8, float(scale)))
            self.kaira.set_scale(self._scale)
            self.strip.set_scale(self._scale)
            self.brand.set_scale(self._scale)
            self._relayout()
        if opacity is not None:
            self._opacity = max(0.30, min(1.0, float(opacity)))
            self.setWindowOpacity(self._opacity)

    def update_pins(self, items: list[tuple[BossDef, BossObservation]]):
        self.strip.set_pins(items)
        self._relayout()

    def patch_pins(self, items: list[tuple[BossDef, BossObservation]]):
        if not self.strip.patch_pins(items):
            self.update_pins(items)

    def update_next(self, settings, observations):
        from ..models import utcnow
        from ..schedule import next_kaira_window

        now = utcnow()
        start, end = next_kaira_window(settings.region or "EU", now)
        if start <= now <= end:
            left = max(0, int((end - now).total_seconds()))
            m, s = divmod(left, 60)
            self.kaira.set_text(f"Kaira · VENTANA {m:02d}:{s:02d}")
        else:
            secs = max(0, int((start - now).total_seconds()))
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            if h > 0:
                self.kaira.set_text(f"Kaira · en {h}h {m:02d}m")
            else:
                self.kaira.set_text(f"Kaira · en {m:02d}:{s:02d}")

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 0.05 if delta > 0 else -0.05
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_appearance(scale=self._scale + step)
        else:
            self.set_appearance(opacity=self._opacity + step)
        self.appearance_changed.emit(self._scale, self._opacity)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            self._moved = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._moved and self._drag is not None:
            self.position_changed.emit(self.x(), self.y())
        self._drag = None
        self._moved = False
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


def make_pins_tab() -> tuple[QWidget, PinStrip]:
    page = QWidget()
    lay = QVBoxLayout(page)
    title = QLabel(
        "Pins · solo vivos o ≤5 min para salir · "
        "<b>#TP</b> · HP en combate"
    )
    title.setWordWrap(True)
    lay.addWidget(title)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    strip = PinStrip()
    strip.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
    scroll.setWidget(strip)
    scroll.setMinimumHeight(200)
    lay.addWidget(scroll)
    lay.addStretch(1)
    return page, strip
