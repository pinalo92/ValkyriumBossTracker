from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from .models import BossDef, BossKind, Teleport
from .resources import package_data_dir

DATA = package_data_dir() / "catalog.json"


@lru_cache(maxsize=1)
def load_raw() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def clear_catalog_cache() -> None:
    load_raw.cache_clear()


def teleports(number_overrides: Optional[dict[str, int]] = None) -> dict[str, Teleport]:
    """Catálogo de TPs. number_overrides = nº de lista in-game confirmados por el usuario."""
    overrides = number_overrides or {}
    out = {}
    for t in load_raw()["teleports"]:
        data = dict(t)
        if data["id"] in overrides:
            data["map_number"] = overrides[data["id"]]
        tp = Teleport(
            id=data["id"],
            name=data["name"],
            map_id=data["map_id"],
            x=data["x"],
            z=data["z"],
            faction=data["faction"],
            name_en=data.get("name_en", ""),
            map_number=data.get("map_number"),
        )
        out[tp.id] = tp
    return out


def format_tp_label(tp: Optional[Teleport], lang: str = "es") -> str:
    """Ej: '#12 Cuartel Costero' o '¿? Cuartel Costero (Coastal Camp)'."""
    if not tp:
        return "—"
    name = tp.name if lang == "es" else (tp.name_en or tp.name)
    if tp.map_number is not None:
        return f"#{tp.map_number} {name}"
    en = f" ({tp.name_en})" if tp.name_en and lang == "es" else ""
    return f"¿? {name}{en}"


def bosses() -> dict[str, BossDef]:
    out = {}
    for b in load_raw()["bosses"]:
        kind = BossKind(b["kind"])
        bd = BossDef(
            id=b["id"],
            name=b["name"],
            name_es=b["name_es"],
            kind=kind,
            map_id=b["map_id"],
            zone=b["zone"],
            faction=b["faction"],
            level=b["level"],
            respawn_minutes=b.get("respawn_minutes"),
            spawn_window_minutes=b.get("spawn_window_minutes", 10),
            nearest_tp_id=b.get("nearest_tp_id", ""),
            x=b.get("x"),
            z=b.get("z"),
            loot_notes=b.get("loot_notes", ""),
            source_note=b.get("source_note", "community-observed"),
            a2tools_field_id=str(b.get("a2tools_field_id") or ""),
        )
        out[bd.id] = bd
    return out


def schedules() -> dict:
    return load_raw().get("schedules", {})


def meta() -> dict:
    return load_raw().get("meta", {})
