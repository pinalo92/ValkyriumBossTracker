# Arquitectura — Pinalo Boss Tracker

## Capas

1. **Catálogo** (`catalog.py` + `data/catalog.json`) — bosses, TPs, horarios community-observed.
2. **Estados / motor** (`engine.py`, `schedule.py`) — fiabilidad, ETA, ruta greedy.
3. **Persistencia** (`storage.py`) — SQLite en `%LOCALAPPDATA%\PinaloBossTracker\`.
4. **Fuentes** (`sources/`) — adapters; MVP = import JSON + estado de conexión informativo.
5. **UI** (`ui/`) — PySide6 dashboard oscuro, modo compacto.

## Flujo

```
Usuario marca vivo/muerto ──► observation SQLite
         │
Fuentes JSON ───────────────► observations
         │
refresh_observation() ──────► Reliability + ETA
         │
build_route() ──────────────► RouteStop[] (score = espera + viaje)
         │
UI tabla + panel ruta
```

## Integraciones externas

Ningún endpoint inventado. Sin API pública documentada de aion2timers/a2tools/atlas para “boss vivo”, el adaptador live queda stubbed vía `sources/status.py` y import local.

## Extender

- Nuevo mapa: entradas en `catalog.json`.
- Nueva fuente: clase `SourceAdapter` + `fetch()` → `BossObservation`.
- Overlay: ventana Qt transparente always-on-top (sin inyección).
