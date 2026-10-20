"""Lee un canal de Discord donde aion2timers (u otro) publica el tablero de bosses.

No lee memoria del juego. Requiere un bot TÚ creas, con permiso Read Messages
en el canal del tablero (https://aion2timers.com/discord-alerts/ → Live board).

Variables / settings:
  discord_bot_token  — token del bot (Bot → Reset Token en Discord Developer Portal)
  discord_channel_id — ID del canal (modo desarrollador → clic derecho → Copiar ID)
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from ..catalog import bosses
from ..engine import mark_killed, mark_seen_alive
from ..models import BossObservation, Reliability, utcnow

API = "https://discord.com/api/v10"


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _boss_index() -> dict[str, str]:
    """normalized name → local boss_id."""
    idx = {}
    for bid, b in bosses().items():
        idx[_normalize(b.name)] = bid
        idx[_normalize(b.name_es)] = bid
    return idx


def fetch_channel_messages(
    bot_token: str, channel_id: str, limit: int = 15, timeout: float = 20.0
) -> list[dict]:
    req = urllib.request.Request(
        f"{API}/channels/{channel_id}/messages?limit={limit}",
        headers={
            "Authorization": f"Bot {bot_token}",
            "User-Agent": "PinaloBossTracker (Discord board sync)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord HTTP {e.code}: {body[:300]}") from e


def _text_blobs(messages: list[dict]) -> str:
    parts: list[str] = []
    for m in messages:
        if m.get("content"):
            parts.append(m["content"])
        for emb in m.get("embeds") or []:
            for key in ("title", "description"):
                if emb.get(key):
                    parts.append(emb[key])
            for f in emb.get("fields") or []:
                parts.append(f"{f.get('name', '')} {f.get('value', '')}")
    return "\n".join(parts)


def parse_board_text(text: str) -> list[BossObservation]:
    """Heurística: busca nombre de boss + palabras vivo/muerto/up/down/spawn/killed."""
    idx = _boss_index()
    catalog = bosses()
    out: list[BossObservation] = []
    seen: set[str] = set()
    lines = re.split(r"[\n\r]+", text)
    alive_kw = re.compile(
        r"\b(up|alive|vivo|spawned|aparec|may be up|window|ventana)\b", re.I
    )
    dead_kw = re.compile(
        r"\b(dead|killed|down|muerto|muerte|respawn|cd|cooldown|timer)\b", re.I
    )

    for line in lines:
        low = _normalize(line)
        if not low:
            continue
        matched_id = None
        for nname, bid in idx.items():
            if nname and nname in low:
                matched_id = bid
                break
        if not matched_id or matched_id in seen:
            continue
        boss = catalog[matched_id]
        if alive_kw.search(line) and not dead_kw.search(line):
            obs = mark_seen_alive(boss, source="discord-board")
            obs.note = "Detectado VIVO/ventana en Discord"
            # Preferir PREDICTED si dice ventana
            if re.search(r"ventana|window|may be up", line, re.I):
                obs.reliability = Reliability.PREDICTED_SPAWN
            out.append(obs)
            seen.add(matched_id)
        elif dead_kw.search(line):
            # Intentar extraer minutos HH:MM o Xm
            when = utcnow()
            m = re.search(r"(\d{1,2}):(\d{2})", line)
            # sin hora de kill fiable → marca muerto ahora (conservador: el timer arranca mal)
            # Mejor: solo marcar muerto si hay "killed" / "muerto" claro
            if re.search(r"\b(killed|muerto|dead|down)\b", line, re.I):
                obs = mark_killed(boss, when=when, source="discord-board")
                obs.note = f"Detectado MUERTO en Discord: {line[:120]}"
                out.append(obs)
                seen.add(matched_id)
    return out


def sync_from_discord(
    bot_token: str, channel_id: str
) -> tuple[list[BossObservation], str]:
    msgs = fetch_channel_messages(bot_token, channel_id)
    text = _text_blobs(msgs)
    if not text.strip():
        return [], "Canal vacío o sin embeds legibles."
    obs = parse_board_text(text)
    note = (
        f"Discord: {len(msgs)} mensajes, {len(obs)} bosses emparejados. "
        "Fuente: tablero/alertas del canal (aion2timers u otro)."
    )
    return obs, note
