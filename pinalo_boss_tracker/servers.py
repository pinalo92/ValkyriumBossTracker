"""Servidores AION 2 Global (nombre + región → serverId A2Tools / CDN).

Los nombres se repiten entre regiones: siempre van con región.
IDs: 1xxx Elyos / 2xxx Asmodian · dígito región (1 NA-E, 2 NA-W, 3 EU, …).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameServer:
    name: str
    region: str  # EU | NA_EAST | NA_WEST | LATAM | ASIA
    faction: str  # elyos | asmodian
    server_id: int
    pair_name: str = ""


def _pair(region: str, base: int, pairs: list[tuple[str, str]]) -> list[GameServer]:
    """base = primer id Elyos de la región (ej. 1301 EU). Asmo = base+1000."""
    out: list[GameServer] = []
    for i, (ely, asm) in enumerate(pairs):
        eid = base + i
        aid = eid + 1000
        out.append(GameServer(ely, region, "elyos", eid, asm))
        out.append(GameServer(asm, region, "asmodian", aid, ely))
    return out


# Pares oficiales (Elyos, Asmodian) por región
_EU = [
    ("Siel", "Israphel"),
    ("Nezekan", "Zikel"),
    ("Vaizel", "Triniel"),
    ("Kaisinel", "Lumiel"),
    ("Yustiel", "Marchutan"),
    ("Ariel", "Azphel"),
    ("Fregion", "Ereshkigal"),
    ("Meslamtaeda", "Beritra"),
    ("Hithanya", "Nemon"),
    ("Nania", "Hadala"),
    ("Tahavatha", "Ludra"),
    ("Luteros", "Ulgorn"),
    ("Phernos", "Munin"),
    ("Daminu", "Odar"),
    ("Kasaka", "Zemurru"),
    ("Bakarma", "Kromede"),
    ("Tsenka", "Quai"),
    ("Kochi", "Baba"),
    ("Ishtar", "Fafnir"),
    ("Tiamat", "Indnath"),
    ("Gauss", "Agnita"),
    ("Lamuatan", "Atiel"),
    ("Nathara", "Tassin"),
]
_NA_EAST = [
    ("Siel", "Israphel"),
    ("Nezekan", "Zikel"),
    ("Vaizel", "Triniel"),
    ("Kaisinel", "Lumiel"),
    ("Yustiel", "Marchutan"),
    ("Ariel", "Azphel"),
    ("Fregion", "Ereshkigal"),
    ("Meslamtaeda", "Beritra"),
    ("Hithanya", "Nemon"),
]
_NA_WEST = [
    ("Siel", "Israphel"),
    ("Nezekan", "Zikel"),
    ("Vaizel", "Triniel"),
    ("Kaisinel", "Lumiel"),
    ("Yustiel", "Marchutan"),
]

SERVERS: list[GameServer] = (
    _pair("EU", 1301, _EU)
    + _pair("NA_EAST", 1101, _NA_EAST)
    + _pair("NA_WEST", 1201, _NA_WEST)
)

REGIONS = ["EU", "NA_EAST", "NA_WEST"]

# lookup rápido
_BY_ID = {s.server_id: s for s in SERVERS}
_BY_KEY = {(s.region, s.name.lower()): s for s in SERVERS}


def servers_for_region(region: str, faction: str | None = None) -> list[GameServer]:
    reg = (region or "EU").upper()
    rows = [s for s in SERVERS if s.region == reg]
    if faction in ("elyos", "asmodian"):
        rows = [s for s in rows if s.faction == faction]
    return rows


def resolve_named_server(
    name: str, region: str = "EU", faction: str | None = None
) -> GameServer | None:
    key = ((region or "EU").upper(), (name or "").strip().lower())
    hit = _BY_KEY.get(key)
    if hit and faction in ("elyos", "asmodian") and hit.faction != faction:
        # nombre mal emparejado con facción → buscar pareja
        for s in SERVERS:
            if s.region == key[0] and s.name.lower() == key[1]:
                return s
        return hit
    return hit


def server_id_for(name: str, region: str = "EU") -> int | None:
    s = resolve_named_server(name, region)
    return s.server_id if s else None


def display_label(s: GameServer) -> str:
    fac = "Elyos" if s.faction == "elyos" else "Asmo"
    return f"{s.name} ({fac})"


def combo_items(region: str, faction: str | None = None) -> list[tuple[str, int]]:
    """[(label, server_id), ...] para QComboBox."""
    return [(display_label(s), s.server_id) for s in servers_for_region(region, faction)]
