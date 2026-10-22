from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class BossKind(str, Enum):
    FIELD = "field"  # respawn after kill
    SCHEDULED = "scheduled"  # Abyss / clock-based


class Reliability(str, Enum):
    CONFIRMED_ALIVE = "CONFIRMADO VIVO"
    PREDICTED_SPAWN = "APARICIÓN PREVISTA"
    KILL_RECORDED = "MUERTE REGISTRADA"
    UNKNOWN = "DESCONOCIDO"
    STALE = "DATOS DESACTUALIZADOS"


@dataclass(frozen=True)
class Teleport:
    id: str
    name: str
    map_id: str
    x: float
    z: float
    faction: str  # elyos | asmodian | both
    name_en: str = ""  # nombre en la lista del mapa del juego
    # Número de la lista de Kibelisks del World Map (in-game). None = aún no confirmado.
    map_number: Optional[int] = None


@dataclass(frozen=True)
class BossDef:
    id: str
    name: str
    name_es: str
    kind: BossKind
    map_id: str
    zone: str
    faction: str
    level: int
    respawn_minutes: Optional[int]  # field bosses
    spawn_window_minutes: int = 10
    nearest_tp_id: str = ""
    x: Optional[float] = None
    z: Optional[float] = None
    loot_notes: str = ""
    source_note: str = "community-observed"
    # ID numérico del feed A2Tools (field / abyss). Vacío = solo match por nombre.
    a2tools_field_id: str = ""


@dataclass
class BossObservation:
    boss_id: str
    source: str
    reliability: Reliability
    updated_at: datetime
    killed_at: Optional[datetime] = None
    predicted_ready_at: Optional[datetime] = None
    predicted_window_end: Optional[datetime] = None
    note: str = ""
    # HP% del feed A2Tools mientras lo pelean (None = sin reporte)
    hp: Optional[int] = None


@dataclass
class RouteStop:
    boss_id: str
    order: int
    reason: str
    score: float
    nearest_tp_id: str
    est_travel_minutes: float
    est_ready_in_minutes: Optional[float]


@dataclass
class AppSettings:
    region: str = "EU"  # EU | NA_EAST | NA_WEST
    server: str = "Kaisinel"  # EU Elyos (pareja Asmodian: Lumiel)
    faction: str = "elyos"
    stale_after_minutes: int = 45
    alert_lead_minutes: int = 5
    max_travel_minutes: float = 25.0
    favorite_boss_ids: list[str] = field(default_factory=list)
    excluded_boss_ids: list[str] = field(default_factory=list)
    preferred_zones: list[str] = field(default_factory=list)
    sound_alerts: bool = True
    compact_mode: bool = False
    # Clave developer a2t_... (catálogo /field-bosses)
    aion2timers_api_key: str = ""
    # Token personal a2p_... (/me/timers = kills vivos/muertos de TU cuenta en el sitio)
    aion2timers_personal_token: str = ""
    # Bot de Discord que lee el canal del tablero aion2timers (auto vivos/muertos)
    discord_bot_token: str = ""
    discord_channel_id: str = ""
    discord_auto_sync: bool = False
    # Feed CDN A2Tools Event Timers (vivos/muertos del servidor, sin clave)
    a2tools_server_id: int = 0  # 0 = auto (prefs A2Tools / nombre)
    a2tools_auto_sync: bool = True
    # Al abrir Valkyrium: abrir Questlog Desktop (DPS / overlays; él se auto-actualiza)
    questlog_launch_on_start: bool = True
    # Si no está instalado: descargar setup oficial (~111 MB) e instalar
    questlog_auto_install: bool = True
    # Legacy: ya no lanza A2Tools; se mantiene por compat con settings.json viejos
    a2tools_launch_on_start: bool = False
    # Arranque: solo overlay en pantalla + icono en bandeja del sistema
    start_in_tray: bool = True
    overlay_on_start: bool = True
    # Si hay update en el manifiesto, instalar al arrancar sin preguntar
    auto_update_on_start: bool = True
    # Overlay visual (1.0 = 100%)
    overlay_scale: float = 1.0
    overlay_opacity: float = 1.0
    # Posición memorizada del overlay (None = centrar / default)
    overlay_x: int | None = None
    overlay_y: int | None = None
    # Wizard de primera vez completado
    wizard_done: bool = False
    # URL JSON de actualización portable: {"version":"0.2.1","url":"https://...zip"}
    update_manifest_url: str = ""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
