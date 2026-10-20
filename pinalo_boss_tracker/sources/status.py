from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..catalog import meta
from .aion2timers_api import resolve_api_key, resolve_personal_token


@dataclass
class ConnectionStatus:
    game: str
    timers_site: str
    dps_meter: str
    catalog: str
    detail: str


def connection_status(
    api_key: Optional[str] = None, personal_token: Optional[str] = None
) -> ConnectionStatus:
    m = meta()
    key = resolve_api_key(api_key)
    pers = resolve_personal_token(personal_token)
    parts = []
    if key:
        parts.append("a2t_ OK (ciclos)")
    else:
        parts.append("sin a2t_")
    if pers:
        parts.append("a2p_ OK → sync vivos/muertos de TU cuenta")
    else:
        parts.append("sin a2p_ (no hay feed vivo/muerto)")
    timers = "Aion2Timers: " + " · ".join(parts)
    return ConnectionStatus(
        game="Sin inyección (modo externo)",
        timers_site=timers,
        dps_meter=(
            "AbyssLogs/A2Tools → aion2timers.com por servidor; "
            "esta app lee solo /me/timers de tu token personal"
        ),
        catalog=f"Local v{m.get('version', '?')} · 61 TP numerados Verteron",
        detail=(
            "Vivo/muerto automático: token personal a2p_ + marcas/meter en el sitio. "
            "Si no: Marcar VIVO/MUERTO o listado Field Boss in-game."
        ),
    )
