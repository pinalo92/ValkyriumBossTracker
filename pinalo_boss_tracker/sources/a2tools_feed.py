"""Feed de field bosses de A2Tools (mismo que Event Timers).

Fuentes (en orden):
  1) Live local (puente WSS interno de Pinalo → data/a2tools-live.json;
     o export opcional del plugin Event Timers → pinalo-live.json)
  2) CDN público: https://cdn.a2tools.app/feeds/boss-timers/{serverId}.json

El serverId se toma de:
  1) settings.a2tools_server_id
  2) %APPDATA%\\com.a2tools.dps-meter\\plugin-data\\event-timers\\prefs.json → lastServer
  3) mapa por nombre (Kaisinel EU → 1304)
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..catalog import bosses
from ..engine import mark_killed, mark_seen_alive
from ..models import BossObservation, Reliability, utcnow
from ..resources import package_data_dir

CDN_FEED = "https://cdn.a2tools.app/feeds/boss-timers/{server}.json"
A2_PLUGIN_DATA = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "com.a2tools.dps-meter"
    / "plugin-data"
    / "event-timers"
)
A2_PREFS = A2_PLUGIN_DATA / "prefs.json"
LIVE_MAX_AGE_MS = 120_000
FIELD_MAP_PATH = package_data_dir() / "a2tools_field_ids.json"

SERVER_NAME_TO_ID = {
    "kaisinel": 1304,
}


def _live_candidates() -> list[Path]:
    from ..paths import app_dir

    return [
        app_dir() / "a2tools-live.json",
        A2_PLUGIN_DATA / "pinalo-live.json",
    ]


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def load_field_map() -> dict[str, dict]:
    if not FIELD_MAP_PATH.exists():
        return {}
    return json.loads(FIELD_MAP_PATH.read_text(encoding="utf-8"))


def read_a2tools_last_server() -> Optional[int]:
    try:
        data = json.loads(A2_PREFS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sid = data.get("lastServer")
    try:
        n = int(sid)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _feed_age_ms(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    at = data.get("at") if isinstance(data, dict) else None
    try:
        at_n = int(at) if at is not None else 0
    except (TypeError, ValueError):
        at_n = 0
    if at_n <= 0:
        try:
            at_n = int(path.stat().st_mtime * 1000)
        except OSError:
            return None
    if at_n < 10_000_000_000:
        at_n *= 1000
    return max(0, int(time.time() * 1000) - at_n)


def live_feed_age_ms() -> Optional[int]:
    ages = [a for a in (_feed_age_ms(p) for p in _live_candidates()) if a is not None]
    return min(ages) if ages else None


def read_live_feed(max_age_ms: int = LIVE_MAX_AGE_MS) -> Optional[dict]:
    best: Optional[tuple[int, dict]] = None
    for path in _live_candidates():
        age = _feed_age_ms(path)
        if age is None or age > max_age_ms:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data.get("bosses"), dict):
            continue
        if best is None or age < best[0]:
            best = (age, data)
    return best[1] if best else None


def resolve_server_id(
    explicit: Optional[int] = None, server_name: str = ""
) -> tuple[int, str]:
    if explicit and int(explicit) > 0:
        return int(explicit), "settings"
    local = read_a2tools_last_server()
    if local:
        return local, "a2tools-prefs"
    key = _normalize(server_name or "")
    if key in SERVER_NAME_TO_ID:
        return SERVER_NAME_TO_ID[key], "name-map"
    return 1304, "default-kaisinel"


def _from_ts(ts) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        n = int(ts)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 10_000_000_000:
        n //= 1000
    return datetime.fromtimestamp(n, tz=timezone.utc)


def _parse_hp(raw) -> Optional[int]:
    """HP% como Event Timers: redondeo 0–100; None si no hay reporte."""
    if raw is None or raw == "":
        return None
    try:
        n = int(round(float(raw)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, n))


def fetch_boss_timers(server_id: int, timeout: float = 20.0) -> dict:
    url = CDN_FEED.format(server=int(server_id))
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PinaloBossTracker/0.2 (A2Tools CDN feed)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"A2Tools CDN HTTP {e.code}: {body[:300]}") from e


def _local_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for bid, b in bosses().items():
        idx[_normalize(b.name)] = bid
        idx[_normalize(b.name_es)] = bid
    return idx


def observations_from_feed(
    feed: dict,
    faction: str = "elyos",
    source: str = "a2tools-cdn",
) -> tuple[list[BossObservation], str]:
    field_map = load_field_map()
    idx = _local_index()
    catalog = bosses()
    remote = feed.get("bosses") or {}
    out: list[BossObservation] = []
    alive = dead = skipped = 0
    with_hp = 0

    for fid, timer in remote.items():
        meta = field_map.get(str(fid)) or {}
        side = (meta.get("side") or "").lower()
        if faction == "elyos" and side == "asmodian":
            continue
        if faction == "asmodian" and side == "elyos":
            continue
        en = meta.get("en") or ""
        es = meta.get("es") or ""
        local_id = idx.get(_normalize(en)) or idx.get(_normalize(es))
        if not local_id or local_id not in catalog:
            skipped += 1
            continue
        boss = catalog[local_id]
        state = (timer.get("state") or "").lower()
        src = timer.get("source") or "?"
        reported = _from_ts(timer.get("reportedAt"))
        next_spawn = _from_ts(timer.get("nextSpawn"))
        up_since = _from_ts(timer.get("upSince"))

        if state == "up":
            obs = mark_seen_alive(boss, source=source)
            obs.reliability = Reliability.CONFIRMED_ALIVE
            # Feed live = confirmación fresca (no marcar STALE por upSince antiguo)
            obs.updated_at = utcnow()
            obs.hp = _parse_hp(timer.get("hp"))
            if obs.hp is not None:
                with_hp += 1
            hp_note = f", HP {obs.hp}%" if obs.hp is not None else ""
            label = "live A2Tools" if source.startswith("a2tools-live") else "feed A2Tools"
            age = ""
            hp_at = _from_ts(timer.get("hpAt"))
            if hp_at and obs.hp is not None:
                age = f" @{hp_at.astimezone().strftime('%H:%M:%S')}"
            elif up_since:
                age = f" up@{up_since.astimezone().strftime('%H:%M:%S')}"
            obs.note = (
                f"Vivo en {label} ({src}{hp_note}{age}). "
                "Comunidad/meters, no lectura directa del cliente."
            )
            alive += 1
            out.append(obs)
            continue

        if state == "dead":
            if next_spawn and boss.respawn_minutes:
                killed_at = next_spawn - timedelta(minutes=boss.respawn_minutes)
            else:
                killed_at = reported or utcnow()
            obs = mark_killed(boss, when=killed_at, source=source)
            obs.hp = None
            if next_spawn:
                obs.predicted_ready_at = next_spawn
                obs.predicted_window_end = next_spawn + timedelta(
                    minutes=boss.spawn_window_minutes
                )
            conf = "confirmado" if timer.get("confirmed") else "sin confirmar"
            obs.note = f"Muerto en feed A2Tools ({src}, {conf})"
            dead += 1
            out.append(obs)
            continue

        skipped += 1

    updated = feed.get("updated") or feed.get("at")
    upd = _from_ts(updated)
    upd_txt = upd.astimezone().strftime("%H:%M:%S") if upd else "?"
    via = "live" if source.startswith("a2tools-live") else "CDN"
    note = (
        f"A2Tools {via} server={feed.get('server')}: "
        f"{alive} vivos ({with_hp} con HP), {dead} muertos, {skipped} sin catálogo. "
        f"Feed ~{upd_txt}."
    )
    return out, note


def sync_from_a2tools(
    server_id: Optional[int] = None,
    server_name: str = "Kaisinel",
    faction: str = "elyos",
    allow_cdn: bool = True,
) -> tuple[list[BossObservation], str, int]:
    sid, how = resolve_server_id(server_id, server_name)
    live = read_live_feed()
    if live:
        try:
            live_sid = int(live.get("server") or 0)
        except (TypeError, ValueError):
            live_sid = 0
        if live_sid > 0:
            sid = live_sid
        src = "a2tools-live"
        if live.get("source") == "a2tools-wss":
            src = "a2tools-live-wss"
        obs, note = observations_from_feed(live, faction=faction, source=src)
        note = f"{note} (serverId {sid} vía live/{how})"
        return obs, note, sid

    if not allow_cdn:
        return [], f"Sin live A2Tools fresco (serverId {sid})", sid

    feed = fetch_boss_timers(sid)
    obs, note = observations_from_feed(feed, faction=faction, source="a2tools-cdn")
    note = f"{note} (serverId {sid} vía {how})"
    return obs, note, sid

