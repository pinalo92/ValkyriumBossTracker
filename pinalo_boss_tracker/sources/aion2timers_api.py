"""Cliente oficial documentado de Aion 2 Timers (Grimvane).

Base: https://aion2.grimvane.app/api/v1
Auth: Authorization: Bearer a2t_... (developer key)
OpenAPI: /api/v1/openapi.json (sin clave)

Importante (docs oficiales):
- GET /field-bosses → catálogo + respawnMin (NO dice si está vivo en tu servidor).
- GET /me/timers → requiere token personal a2p_ (kills que TU cuenta guardó en el sitio).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..catalog import bosses, format_tp_label, teleports
from ..engine import distance_tp_to_boss, mark_killed, mark_seen_alive, tp_for
from ..models import BossDef, BossObservation, Reliability
from ..storage import load_tp_numbers

API_BASE = "https://aion2.grimvane.app/api/v1"


@dataclass
class RemoteFieldBoss:
    id: str
    name: str
    zone: str
    location: str
    level: Optional[int]
    respawn_min: int


@dataclass
class BossWithTp:
    local: BossDef
    remote: Optional[RemoteFieldBoss]
    tp_name: str
    tp_id: str
    dist_units: Optional[float]


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def resolve_api_key(explicit: Optional[str] = None) -> Optional[str]:
    key = (explicit or "").strip()
    if key:
        return key
    return (os.environ.get("PINALO_A2T_KEY") or os.environ.get("A2T_API_KEY") or "").strip() or None


def resolve_personal_token(explicit: Optional[str] = None) -> Optional[str]:
    tok = (explicit or "").strip()
    if tok:
        return tok
    return (
        os.environ.get("PINALO_A2T_PERSONAL") or os.environ.get("A2T_PERSONAL_TOKEN") or ""
    ).strip() or None


def _api_get(path: str, bearer: str, timeout: float = 20.0) -> dict | list:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
            "User-Agent": "PinaloBossTracker/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Aion2Timers HTTP {e.code}: {body[:400]}") from e


def _parse_stamp(stamp) -> Optional[datetime]:
    if not stamp:
        return None
    if isinstance(stamp, str):
        raw = stamp
    else:
        raw = stamp.get("at")
    if not raw:
        return None
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fetch_field_bosses(api_key: str, timeout: float = 20.0) -> list[RemoteFieldBoss]:
    data = _api_get("/field-bosses", api_key, timeout)
    items = data if isinstance(data, list) else data.get("bosses") or data.get("fieldBosses") or []
    out: list[RemoteFieldBoss] = []
    for b in items:
        out.append(
            RemoteFieldBoss(
                id=b["id"],
                name=b["name"],
                zone=b.get("zone", ""),
                location=b.get("location", ""),
                level=b.get("level"),
                respawn_min=int(b["respawnMin"]),
            )
        )
    return out


def fetch_my_field_boss_timers(
    personal_token: str, zone: str = "Europe/Berlin", timeout: float = 20.0
) -> list[dict]:
    """GET /me/timers → fieldBosses con killed / respawns / up (token a2p_)."""
    q = f"?zone={urllib.parse.quote(zone)}" if zone else ""
    data = _api_get(f"/me/timers{q}", personal_token, timeout)
    if not isinstance(data, dict):
        return []
    return list(data.get("fieldBosses") or [])


def match_remote_name_to_local(name: str) -> Optional[str]:
    """Devuelve boss_id local o None."""
    target = _normalize(name)
    for bid, boss in bosses().items():
        if _normalize(boss.name) == target:
            return bid
    return None


def observations_from_my_timers(
    field_bosses: list[dict],
) -> tuple[list[BossObservation], str]:
    """Convierte /me/timers.fieldBosses en observaciones locales.

    - up=true → ventana/posible vivo (no es confirmación in-game)
    - up=false + killed → muerte registrada + ETA
    """
    catalog = bosses()
    out: list[BossObservation] = []
    alive = dead = skipped = 0
    for fb in field_bosses:
        bid = match_remote_name_to_local(fb.get("name", ""))
        if not bid or bid not in catalog:
            skipped += 1
            continue
        boss = catalog[bid]
        killed_at = _parse_stamp(fb.get("killed"))
        up = bool(fb.get("up"))
        if up:
            obs = mark_seen_alive(boss, source="aion2timers-/me/timers")
            obs.note = (
                "up=true en Aion2Timers (ciclo cumplido / posible vivo; "
                "NO es el listado Field Boss del juego)"
            )
            obs.reliability = Reliability.PREDICTED_SPAWN
            if killed_at:
                obs.killed_at = killed_at
            alive += 1
        elif killed_at:
            obs = mark_killed(boss, when=killed_at, source="aion2timers-/me/timers")
            obs.note = "Muerte según cuenta Aion2Timers (/me/timers)"
            dead += 1
        else:
            skipped += 1
            continue
        out.append(obs)
    note = (
        f"Sync personal: {alive} posibles vivos/ventana, {dead} muertos con timer, "
        f"{skipped} sin emparejar. Fuente: tu cuenta en aion2.grimvane.app "
        "(meter/marcas/share), no lectura del juego."
    )
    return out, note


def match_remote_to_local(remote: list[RemoteFieldBoss]) -> dict[str, RemoteFieldBoss]:
    """Map local catalog boss_id → remote entry by English name."""
    by_norm = {_normalize(r.name): r for r in remote}
    mapped: dict[str, RemoteFieldBoss] = {}
    for bid, boss in bosses().items():
        hit = by_norm.get(_normalize(boss.name))
        if hit:
            mapped[bid] = hit
    return mapped


def bosses_with_nearest_tp(
    api_key: Optional[str] = None,
) -> tuple[list[BossWithTp], str]:
    """Lista local + TP. Si hay API key, enriquece con datos remotos."""
    key = resolve_api_key(api_key)
    remote_map: dict[str, RemoteFieldBoss] = {}
    note = "Solo catálogo local (sin clave API)."
    if key:
        remote = fetch_field_bosses(key)
        remote_map = match_remote_to_local(remote)
        note = (
            f"API OK: {len(remote)} bosses remotos, "
            f"{len(remote_map)} emparejados. "
            "Esto NO indica vivos en tu servidor — solo zona/ciclo."
        )

    overrides = load_tp_numbers()
    rows: list[BossWithTp] = []
    for bid, boss in bosses().items():
        tp = tp_for(boss, overrides)
        rows.append(
            BossWithTp(
                local=boss,
                remote=remote_map.get(bid),
                tp_name=format_tp_label(tp),
                tp_id=tp.id if tp else "",
                dist_units=distance_tp_to_boss(boss),
            )
        )
    return rows, note


def format_tp_guide(faction: str = "elyos", api_key: Optional[str] = None) -> str:
    rows, note = bosses_with_nearest_tp(api_key)
    lines = [
        "Boss → TP más cercano (catálogo Pinalo)",
        note,
        "",
    ]
    for row in rows:
        b = row.local
        if faction == "elyos" and b.faction == "asmodian":
            continue
        if faction == "asmodian" and b.faction == "elyos":
            continue
        loc = row.remote.location if row.remote else b.zone
        cycle = (
            f"{row.remote.respawn_min} min (API)"
            if row.remote
            else (f"{b.respawn_minutes} min" if b.respawn_minutes else "programado")
        )
        dist = f"{row.dist_units:.0f} u" if row.dist_units is not None else "—"
        lines.append(
            f"- {b.name_es} | {loc}\n"
            f"  TP: {row.tp_name}  |  dist. ~{dist}  |  ciclo {cycle}"
        )
    return "\n".join(lines)
