from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from .catalog import bosses, teleports
from .models import (
    AppSettings,
    BossDef,
    BossKind,
    BossObservation,
    Reliability,
    RouteStop,
    utcnow,
)
from .schedule import scheduled_observation


def haversine_minutes(x1: float, z1: float, x2: float, z2: float, speed_mpm: float = 80.0) -> float:
    """Heuristic travel minutes from planar map units (not real pathing)."""
    dist = math.hypot(x1 - x2, z1 - z2)
    # map units ≈ metres in our catalog; flying/TP reduces effective cost
    walk = dist / speed_mpm
    # assume player TPs first: base 1.5 min + short approach
    return 1.5 + min(walk, 12.0)


def tp_for(boss: BossDef, number_overrides: dict[str, int] | None = None):
    tps = teleports(number_overrides)
    return tps.get(boss.nearest_tp_id)


def distance_tp_to_boss(boss: BossDef) -> Optional[float]:
    tp = tp_for(boss)
    if not tp or boss.x is None or boss.z is None:
        return None
    return math.hypot(tp.x - boss.x, tp.z - boss.z)


def refresh_observation(
    boss: BossDef,
    existing: Optional[BossObservation],
    settings: AppSettings,
    now: Optional[datetime] = None,
) -> BossObservation:
    now = now or utcnow()
    if boss.kind == BossKind.SCHEDULED:
        return scheduled_observation(boss.id, settings.region, existing=existing)

    if existing is None:
        return BossObservation(
            boss_id=boss.id,
            source="none",
            reliability=Reliability.UNKNOWN,
            updated_at=now,
            note="Sin marca de muerte aún. Usa el listado in-game o marca una muerte.",
        )

    age_min = (now - existing.updated_at).total_seconds() / 60.0
    obs = BossObservation(
        boss_id=existing.boss_id,
        source=existing.source,
        reliability=existing.reliability,
        updated_at=existing.updated_at,
        killed_at=existing.killed_at,
        predicted_ready_at=existing.predicted_ready_at,
        predicted_window_end=existing.predicted_window_end,
        note=existing.note,
        hp=existing.hp,
    )

    if age_min > settings.stale_after_minutes and obs.reliability == Reliability.CONFIRMED_ALIVE:
        obs.reliability = Reliability.STALE
        obs.note = (obs.note + " | ").strip(" |") + "Confirmación antigua"
        return obs

    if obs.killed_at and boss.respawn_minutes:
        ready = obs.killed_at + timedelta(minutes=boss.respawn_minutes)
        window_end = ready + timedelta(minutes=boss.spawn_window_minutes)
        obs.predicted_ready_at = ready
        obs.predicted_window_end = window_end
        if now < ready:
            obs.reliability = Reliability.KILL_RECORDED
            obs.note = "Muerte registrada; esperando ciclo (estimado)"
        elif ready <= now <= window_end:
            obs.reliability = Reliability.PREDICTED_SPAWN
            obs.note = "Ventana de aparición estimada (NO confirmado vivo)"
        elif now > window_end:
            # past window without confirmation
            if obs.reliability != Reliability.CONFIRMED_ALIVE:
                obs.reliability = Reliability.UNKNOWN
                obs.note = "Ventana estimada ya pasó; estado desconocido"
    return obs


def mark_killed(boss: BossDef, when: Optional[datetime] = None, source: str = "manual") -> BossObservation:
    when = when or utcnow()
    ready = None
    end = None
    if boss.respawn_minutes:
        ready = when + timedelta(minutes=boss.respawn_minutes)
        end = ready + timedelta(minutes=boss.spawn_window_minutes)
    return BossObservation(
        boss_id=boss.id,
        source=source,
        reliability=Reliability.KILL_RECORDED,
        updated_at=utcnow(),
        killed_at=when,
        predicted_ready_at=ready,
        predicted_window_end=end,
        note="Muerte marcada manualmente",
    )


def mark_seen_alive(boss: BossDef, source: str = "manual") -> BossObservation:
    return BossObservation(
        boss_id=boss.id,
        source=source,
        reliability=Reliability.CONFIRMED_ALIVE,
        updated_at=utcnow(),
        note="Marcado como visto vivo por el usuario (no feed automático)",
    )


def mark_unavailable(boss: BossDef) -> BossObservation:
    return BossObservation(
        boss_id=boss.id,
        source="manual",
        reliability=Reliability.UNKNOWN,
        updated_at=utcnow(),
        note="Marcado inaccesible / no encontrado",
    )


def minutes_until(dt: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
    if not dt:
        return None
    now = now or utcnow()
    return (dt - now).total_seconds() / 60.0


def build_route(
    settings: AppSettings,
    observations: dict[str, BossObservation],
    now: Optional[datetime] = None,
    max_stops: int = 8,
) -> list[RouteStop]:
    """Score bosses by readiness + travel; greedy chain from densest ready cluster."""
    now = now or utcnow()
    all_bosses = bosses()
    tps = teleports()
    candidates: list[tuple[float, BossDef, BossObservation, float, float]] = []

    for bid, boss in all_bosses.items():
        if bid in settings.excluded_boss_ids:
            continue
        if settings.faction == "elyos" and boss.faction == "asmodian":
            continue
        if settings.faction == "asmodian" and boss.faction == "elyos":
            continue
        if settings.preferred_zones and boss.zone not in settings.preferred_zones:
            # soft filter: still allow if favorite
            if bid not in settings.favorite_boss_ids:
                pass  # keep all for MVP; preferred zones boost score only
        obs = refresh_observation(boss, observations.get(bid), settings, now)
        ready_in = 0.0
        if obs.reliability == Reliability.CONFIRMED_ALIVE:
            ready_in = 0.0
        elif obs.predicted_ready_at:
            ready_in = max(0.0, minutes_until(obs.predicted_ready_at, now) or 0.0)
        else:
            ready_in = 9999.0

        tp = tps.get(boss.nearest_tp_id)
        travel = 8.0
        if tp and boss.x is not None and boss.z is not None:
            travel = haversine_minutes(tp.x, tp.z, boss.x, boss.z)
        if travel > settings.max_travel_minutes and bid not in settings.favorite_boss_ids:
            continue

        # score: lower is better
        score = ready_in * 1.4 + travel
        if bid in settings.favorite_boss_ids:
            score -= 8
        if obs.reliability == Reliability.CONFIRMED_ALIVE:
            score -= 15
        elif obs.reliability == Reliability.PREDICTED_SPAWN:
            score -= 5
        elif obs.reliability == Reliability.UNKNOWN:
            score += 20
        if settings.preferred_zones and boss.zone in settings.preferred_zones:
            score -= 3
        # combat estimate
        score += 2.5
        candidates.append((score, boss, obs, ready_in, travel))

    if not candidates:
        return []

    candidates.sort(key=lambda x: x[0])
    # greedy path: start with best, then nearest next among remaining
    route: list[RouteStop] = []
    remaining = candidates[:]
    _, first_boss, first_obs, first_ready, first_travel = remaining.pop(0)
    route.append(
        RouteStop(
            boss_id=first_boss.id,
            order=1,
            reason=_reason(first_obs, first_ready, first_travel),
            score=0,
            nearest_tp_id=first_boss.nearest_tp_id,
            est_travel_minutes=first_travel,
            est_ready_in_minutes=None if first_ready >= 9000 else first_ready,
        )
    )
    cur = first_boss
    while remaining and len(route) < max_stops:
        best_i = None
        best_val = None
        for i, (sc, boss, obs, ready, travel) in enumerate(remaining):
            # chain cost: ready wait + map hop heuristic
            hop = 5.0
            if cur.x is not None and boss.x is not None:
                hop = haversine_minutes(cur.x or 0, cur.z or 0, boss.x, boss.z, speed_mpm=120)
            # same-map bonus
            if boss.map_id == cur.map_id:
                hop *= 0.7
            val = ready * 1.2 + hop + (0 if obs.reliability == Reliability.CONFIRMED_ALIVE else 3)
            if boss.id in settings.favorite_boss_ids:
                val -= 4
            if best_val is None or val < best_val:
                best_val = val
                best_i = i
        sc, boss, obs, ready, travel = remaining.pop(best_i)
        route.append(
            RouteStop(
                boss_id=boss.id,
                order=len(route) + 1,
                reason=_reason(obs, ready, travel),
                score=best_val or 0,
                nearest_tp_id=boss.nearest_tp_id,
                est_travel_minutes=travel,
                est_ready_in_minutes=None if ready >= 9000 else ready,
            )
        )
        cur = boss
    return route


def _reason(obs: BossObservation, ready_in: float, travel: float) -> str:
    parts = [obs.reliability.value]
    if ready_in < 9000:
        if ready_in <= 0:
            parts.append("listo ahora (estimado o confirmado)")
        else:
            parts.append(f"listo en ~{ready_in:.0f} min")
    parts.append(f"viaje est. ~{travel:.0f} min (heurística TP)")
    if obs.note:
        parts.append(obs.note)
    return " · ".join(parts)


def format_duration(mins: float) -> str:
    """1h 05m / 42m / <1m."""
    total = max(0, int(mins))
    h, m = divmod(total, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    if m > 0:
        return f"{m}m"
    return "<1m"


def format_alive_dead(obs: BossObservation, now: Optional[datetime] = None) -> str:
    """Solo lo que importa: VIVO / MUERTO / VENTANA / ?"""
    now = now or utcnow()
    if obs.reliability == Reliability.CONFIRMED_ALIVE:
        return "VIVO"
    if (
        obs.predicted_ready_at
        and obs.predicted_window_end
        and obs.predicted_ready_at <= now <= obs.predicted_window_end
    ):
        return "VENTANA"
    if obs.reliability == Reliability.KILL_RECORDED and obs.predicted_ready_at:
        if now < obs.predicted_ready_at:
            return "MUERTO"
    if obs.reliability == Reliability.PREDICTED_SPAWN:
        # Esperando próxima ventana (p.ej. Kaira): no marcar VENTANA o
        # el filtro de pins (≤5 min) lo mostraría siempre.
        if obs.predicted_ready_at and now < obs.predicted_ready_at:
            return "MUERTO"
        return "¿?"
    if obs.reliability == Reliability.STALE:
        return "¿?"
    return "¿?"


def format_countdown(obs: BossObservation, now: Optional[datetime] = None) -> str:
    """Texto corto para la columna Revivir."""
    now = now or utcnow()
    if obs.reliability == Reliability.CONFIRMED_ALIVE:
        return "ahora"
    if obs.predicted_ready_at and now < obs.predicted_ready_at:
        mins = minutes_until(obs.predicted_ready_at, now) or 0
        clock = obs.predicted_ready_at.astimezone().strftime("%H:%M")
        return f"{format_duration(mins)} (~{clock})"
    if (
        obs.predicted_ready_at
        and obs.predicted_window_end
        and obs.predicted_ready_at <= now <= obs.predicted_window_end
    ):
        left = minutes_until(obs.predicted_window_end, now) or 0
        return f"{format_duration(left)} restantes"
    if obs.reliability == Reliability.UNKNOWN:
        return "—"
    return "—"


def format_tp_number(tp) -> str:
    if not tp:
        return "—"
    if tp.map_number is not None:
        return f"#{tp.map_number}"
    return "¿?"


def is_abyss_boss(boss: BossDef) -> bool:
    """Abismo / Reshanta (scheduled o zona Reshanta)."""
    if boss.kind == BossKind.SCHEDULED:
        return True
    mid = (boss.map_id or "").lower()
    zone = (boss.zone or "").lower()
    return "reshanta" in mid or "reshanta" in zone or "abismo" in zone


def format_wb_clipboard(boss: BossDef, tp=None) -> str:
    """Texto para chat al clic: field = WB nombre TP nº · abismo = WB abismo nombre."""
    name = (boss.name_es or boss.name or boss.id).strip()
    if is_abyss_boss(boss):
        return f"WB abismo {name}"
    if tp is not None and getattr(tp, "map_number", None) is not None:
        return f"WB {name} TP {int(tp.map_number)}"
    return f"WB {name}"
