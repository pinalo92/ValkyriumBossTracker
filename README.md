# Pinalo Boss Tracker

Asistente de farmeo de **field bosses** para **AION 2 Global EU/NA** (Windows 11).

## Qué hace (MVP 0.1)

- Lista bosses de **Verteron (Elyos)** + **Watcher Kaira** programado.
- Estados de fiabilidad: CONFIRMADO VIVO · APARICIÓN PREVISTA · MUERTE REGISTRADA · DESCONOCIDO · DATOS DESACTUALIZADOS.
- Marca manual: vivo / muerto / inaccesible.
- Cuenta atrás estimada a partir del ciclo de respawn (datos community-observed).
- TP más cercano del catálogo y distancia heurística.
- **Ruta automática** por espera + viaje (no solo por hora).
- Importación de eventos JSON.
- Preferencias SQLite en `%LOCALAPPDATA%\PinaloBossTracker\`.
- Modo compacto.

## Aion2Timers API (real, documentada)

Base: `https://aion2.grimvane.app/api/v1` · OpenAPI sin clave.

1. Entra en [aion2.grimvane.app](https://aion2.grimvane.app/abyss-boss-timers/), crea cuenta (guest vale) → **Developer keys** → clave `a2t_...`.
2. Pégala en la app o define `PINALO_A2T_KEY`.
3. Pulsa **Sincronizar + TP**.

| Ruta | Qué da | Qué NO da |
|------|--------|-----------|
| `/field-bosses` | Nombre, zona, ubicación, `respawnMin` | Si está vivo en **tu** servidor |
| `/me/timers` | Kills que **tu** cuenta guardó (token `a2p_`) | Feed global de todos los meters |

La app ya mapea cada boss al **TP más cercano** del catálogo y lo muestra en la tabla y en la ruta (`→ Ve al TP: …`).

## Qué NO hace (y por qué)

| Capacidad | Estado |
|-----------|--------|
| “Boss vivo ahora” sin tu clave/cuenta | **No** — la API pública de ciclos no es un feed live por servidor |
| Lectura de paquetes del juego / DPS meter | **No** — riesgo ToS; no se inyecta ni captura memoria |
| Overlay inyectado en el cliente | **No** — solo ventana externa Windows |
| Distancia = tiempo real de vuelo | **No** — heurística de mapa; corrige con marcas |

La fuente de verdad del servidor sigue siendo el **listado Field Boss in-game**.

## Fuentes estudiadas

- https://aion2timers.com/ — timers + kills vía meters/comunidad; **sin API pública documentada**.
- https://a2tools.app/ — DPS meter (Npc); no integrado.
- https://aion2atlas.app/boss-timer/ — ciclos de respawn community-observed.
- https://aion2vault.com/builds/world-boss-timer/ — catálogo TP / zonas.
- https://github.com/cyberbadger6969/aion2-dps-meter — meter Global; no se embebe.

Ciclos de respawn del catálogo: promedios community (Atlas/Timers, oct 2026), **no oficiales NCSOFT**.

## Arquitectura

```
pinalo_boss_tracker/
  catalog.py / data/catalog.json   # bosses, TPs, schedules
  engine.py                        # estados + ruta
  schedule.py                      # Kaira programado
  storage.py                       # SQLite prefs/historial
  sources/                         # adapters (JSON import)
  ui/                              # PySide6 dashboard
```

## Instalación

```bat
cd PinaloBossTracker
python -m pip install -r requirements.txt
python -m pip install tzdata
run.bat
```

O:

```bat
python -m pinalo_boss_tracker
```

### EXE portable (recomendado)

Incluye UI, caras, catálogo, websockets y modo portable (`.\data` junto al exe):

```bat
build_exe.bat
```

Salida:

- `dist\PinaloBossTracker_Portable\Iniciar_Portable.bat` — cópialo a USB/otra carpeta
- `dist\PinaloBossTracker\PinaloBossTracker.exe` — mismo build

## Uso rápido

1. Elige **EU** y **elyos**.
2. Cuando mates un boss → **Marcar MUERTO** (arranca ETA).
3. Si lo ves up → **Marcar VIVO**.
4. Pulsa **Recalcular ruta**.
5. Opcional: importa `examples/kills.example.json`.

## Tests

```bat
python -m pytest -q
```

## Actualizar / desinstalar

- Actualizar: sustituye la carpeta del proyecto y reinstala `requirements.txt`.
- Desinstalar: borra la carpeta del proyecto y `%LOCALAPPDATA%\PinaloBossTracker\`.

## Roadmap

- Adaptador Discord/webhook si la comunidad publica formato estable.
- Mapa interactivo 2D con flechas de ruta.
- Overlay always-on-top transparente (sin inyección).
- Sonidos / hotkeys / bandeja del sistema.
- Catálogo Altgard/Eltnen cuando lo pidas.
