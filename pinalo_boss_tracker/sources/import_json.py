from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..models import BossObservation, Reliability
from .base import SourceAdapter


class JsonKillImportAdapter(SourceAdapter):
    """Import kill/seen events from a local JSON file.

    Expected format:
    {
      "events": [
        {"boss_id": "kernon_west", "type": "kill", "at": "2026-10-19T18:00:00+00:00", "source": "manual"},
        {"boss_id": "lawa", "type": "seen_alive", "at": "2026-10-19T19:00:00+00:00"}
      ]
    }
    """

    name = "json-import"

    def __init__(self, path: Path):
        self.path = path

    def fetch(self) -> list[BossObservation]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        out: list[BossObservation] = []
        for ev in data.get("events", []):
            at = datetime.fromisoformat(ev["at"])
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            typ = ev.get("type", "kill")
            if typ == "seen_alive":
                out.append(
                    BossObservation(
                        boss_id=ev["boss_id"],
                        source=ev.get("source", self.name),
                        reliability=Reliability.CONFIRMED_ALIVE,
                        updated_at=at,
                        note="Importado como visto vivo",
                    )
                )
            else:
                out.append(
                    BossObservation(
                        boss_id=ev["boss_id"],
                        source=ev.get("source", self.name),
                        reliability=Reliability.KILL_RECORDED,
                        updated_at=at,
                        killed_at=at,
                        note="Importado como muerte",
                    )
                )
        return out
