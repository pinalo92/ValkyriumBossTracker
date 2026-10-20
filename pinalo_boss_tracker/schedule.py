from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .catalog import schedules
from .models import BossObservation, Reliability, utcnow


def next_kaira_window(region: str, now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Return (window_start_utc, window_end_utc) for Watcher Kaira."""
    now = now or utcnow()
    sched = schedules()["kaira_watcher"]
    tz_name = sched["timezone_by_region"].get(region, "Europe/Berlin")
    tz = ZoneInfo(tz_name)
    local = now.astimezone(tz)
    hours = list(sched["hours_server"])
    duration = int(sched["duration_minutes"])

    candidates = []
    for day_offset in range(0, 3):
        day = (local + timedelta(days=day_offset)).date()
        for h in hours:
            start_local = datetime(day.year, day.month, day.day, h, 0, tzinfo=tz)
            end_local = start_local + timedelta(minutes=duration)
            candidates.append((start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)))

    for start, end in candidates:
        if end > now:
            return start, end
    # fallback
    return candidates[0]


def scheduled_observation(
    boss_id: str,
    region: str,
    existing: Optional[BossObservation] = None,
) -> BossObservation:
    now = utcnow()
    if boss_id != "kaira_watcher":
        return BossObservation(
            boss_id=boss_id,
            source="catalog-schedule",
            reliability=Reliability.UNKNOWN,
            updated_at=now,
            note="Sin horario programado en catálogo",
        )
    start, end = next_kaira_window(region, now)

    # Muerte marcada en la ventana actual → no tratar como "vivo/ahora"
    if (
        existing
        and existing.killed_at
        and start <= existing.killed_at <= end
        and now <= end
    ):
        nxt_start, nxt_end = next_kaira_window(region, end + timedelta(seconds=1))
        return BossObservation(
            boss_id=boss_id,
            source=existing.source or "manual",
            reliability=Reliability.KILL_RECORDED,
            updated_at=now,
            killed_at=existing.killed_at,
            predicted_ready_at=nxt_start,
            predicted_window_end=nxt_end,
            note="Kaira marcada muerta en esta ventana (no es Activo)",
        )

    if start <= now <= end:
        rel = Reliability.PREDICTED_SPAWN
        note = "Ventana de spawn (horario) — no confirma que esté vivo in-game"
    else:
        rel = Reliability.PREDICTED_SPAWN
        note = "Próxima ventana programada (community-observed)"
    return BossObservation(
        boss_id=boss_id,
        source="catalog-schedule",
        reliability=rel,
        updated_at=now,
        predicted_ready_at=start,
        predicted_window_end=end,
        note=note,
    )
