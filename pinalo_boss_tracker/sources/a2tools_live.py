"""Cliente live oculto del feed de field bosses de A2Tools.



Misma fuente que Event Timers (meter):

  wss://a2tools.app/api/boss-timers/live?server={id}

  → envía {"op":"follow","bosses":["101001", ...]}

  → recibe state/boss con HP en combate.



No abre UI de A2Tools. Escribe un snapshot local que lee a2tools_feed.

"""



from __future__ import annotations



import asyncio

import json

import threading

import time

from typing import Callable, Optional



from ..paths import app_dir



LIVE_URL = "wss://a2tools.app/api/boss-timers/live?server={server}"

LIVE_FILE_NAME = "a2tools-live.json"

MAX_FOLLOW = 50

PING_EVERY_S = 30.0





def live_snapshot_path():

    return app_dir() / LIVE_FILE_NAME





def write_live_snapshot(feed: dict):

    path = live_snapshot_path()

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(".tmp")

    now_ms = int(feed.get("at") or time.time() * 1000)

    payload = {

        "format": "pinalo-live-v1",

        "server": feed.get("server"),

        "at": now_ms,

        "updated": now_ms // 1000,

        "bosses": feed.get("bosses") or {},

        "source": "a2tools-wss",

    }

    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    tmp.replace(path)

    return path





def _num(v) -> float:

    try:

        return float(v)

    except (TypeError, ValueError):

        return 0.0





def _same_life(a: dict, b: dict) -> bool:

    return (

        a.get("state") == "up"

        and b.get("state") == "up"

        and (

            not a.get("upSince")

            or not b.get("upSince")

            or _num(a.get("upSince")) == _num(b.get("upSince"))

        )

    )





def merge_boss_entry(have: Optional[dict], entry: dict) -> dict:

    """Misma lógica que Event Timers (pins.js / mergeOwn): no perder HP mid-fight."""

    if not isinstance(entry, dict):

        return have or {}

    if not have:

        return dict(entry)



    have_rep = _num(have.get("reportedAt"))

    entry_rep = _num(entry.get("reportedAt"))



    if have_rep <= entry_rep:

        # Informe más nuevo: si es la misma vida y viene sin HP, conservar el conocido.

        if (

            _same_life(have, entry)

            and entry.get("hp") is None

            and have.get("hp") is not None

        ):

            return {**entry, "hp": have["hp"], "hpAt": have.get("hpAt")}

        out = dict(entry)

        # Si el nuevo trae HP más fresco aunque reportedAt sea igual/nuevo

        if (

            _same_life(have, entry)

            and entry.get("hp") is not None

            and _num(entry.get("hpAt")) < _num(have.get("hpAt"))

            and have.get("hp") is not None

        ):

            # No pisar un HP más reciente con uno viejo embebido en el state

            out["hp"] = have["hp"]

            out["hpAt"] = have.get("hpAt")

        return out



    # Informe más viejo, pero puede traer HP más nuevo (hpAt)

    if (

        _same_life(have, entry)

        and entry.get("hp") is not None

        and _num(entry.get("hpAt")) > _num(have.get("hpAt"))

    ):

        return {**have, "hp": entry["hp"], "hpAt": entry.get("hpAt")}

    return have





class A2ToolsLiveBridge:

    """Hilo con asyncio: mantiene WSS y actualiza el snapshot + callback."""



    def __init__(

        self,

        on_update: Optional[Callable[[dict], None]] = None,

        on_status: Optional[Callable[[str], None]] = None,

    ):

        self._on_update = on_update

        self._on_status = on_status

        self._thread: Optional[threading.Thread] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._wake: Optional[asyncio.Event] = None

        self._stop = threading.Event()

        self._server = 0

        self._follow: list[str] = []

        self._follow_lock = threading.Lock()

        self._bosses: dict = {}

        self.connected = False



    @property

    def running(self) -> bool:

        return self._thread is not None and self._thread.is_alive()



    def start(self, server_id: int, boss_ids: list[str]) -> None:

        self._server = int(server_id)

        self.set_follow(boss_ids)

        if self.running:

            return

        self._stop.clear()

        self._thread = threading.Thread(

            target=self._thread_main, name="a2tools-live", daemon=True

        )

        self._thread.start()



    def stop(self) -> None:

        self._stop.set()

        wake = self._wake

        loop = self._loop

        if loop and loop.is_running() and wake is not None:

            loop.call_soon_threadsafe(wake.set)

        if self._thread and self._thread.is_alive():

            self._thread.join(timeout=2.5)

        self._thread = None

        self._loop = None

        self._wake = None

        self.connected = False



    def set_follow(self, boss_ids: list[str]) -> None:

        cleaned: list[str] = []

        seen: set[str] = set()

        for b in boss_ids:

            s = str(b).strip()

            if not s or not s.isdigit() or s in seen:

                continue

            seen.add(s)

            cleaned.append(s)

            if len(cleaned) >= MAX_FOLLOW:

                break

        cleaned.sort()

        with self._follow_lock:

            if cleaned == self._follow:

                return

            self._follow = cleaned

        wake = self._wake

        loop = self._loop

        if loop and loop.is_running() and wake is not None:

            loop.call_soon_threadsafe(wake.set)



    def snapshot(self) -> dict:

        return {

            "server": self._server,

            "at": int(time.time() * 1000),

            "bosses": dict(self._bosses),

            "source": "a2tools-wss",

        }



    def _status(self, msg: str) -> None:

        if self._on_status:

            try:

                self._on_status(msg)

            except Exception:

                pass



    def _emit(self) -> None:
        feed = self.snapshot()
        # Primero callback UI (HP); disco en segundo plano cada ~0.8s
        if self._on_update:
            try:
                self._on_update(feed)
            except Exception:
                pass
        now = time.monotonic()
        last = getattr(self, '_last_disk_write', 0.0)
        if now - last >= 0.8:
            self._last_disk_write = now
            try:
                write_live_snapshot(feed)
            except OSError:
                pass



    def _thread_main(self) -> None:

        try:

            asyncio.run(self._async_main())

        except Exception as e:

            self._status(f"live error: {e}")



    async def _async_main(self) -> None:

        self._loop = asyncio.get_running_loop()

        self._wake = asyncio.Event()

        while not self._stop.is_set():

            with self._follow_lock:

                follow = list(self._follow)

                server = self._server

            if not server or not follow:

                self._status("live: esperando server/bosses")

                try:

                    await asyncio.wait_for(self._wake.wait(), timeout=2.0)

                except asyncio.TimeoutError:

                    pass

                self._wake.clear()

                continue

            try:

                await self._session(server, follow)

            except Exception as e:

                self.connected = False

                self._status(f"live reconnect: {e}")

                await asyncio.sleep(1.5)



    async def _session(self, server: int, follow: list[str]) -> None:

        import websockets



        url = LIVE_URL.format(server=server)

        self._status(f"live connecting {server}…")

        async with websockets.connect(

            url,

            open_timeout=12,

            ping_interval=None,

            max_queue=64,

            additional_headers={

                "Origin": "https://a2tools.app",

                "User-Agent": "PinaloBossTracker/0.3 (live bridge)",

            },

        ) as ws:

            await ws.send(json.dumps({"op": "follow", "bosses": follow}))

            self.connected = True

            self._status(f"live OK server={server} ({len(follow)} bosses)")

            last_ping = time.monotonic()

            while not self._stop.is_set():

                with self._follow_lock:

                    now_follow = list(self._follow)

                    now_server = self._server

                if now_server != server:

                    return

                if now_follow != follow:

                    follow = now_follow

                    if not follow:

                        return

                    await ws.send(json.dumps({"op": "follow", "bosses": follow}))



                if time.monotonic() - last_ping >= PING_EVERY_S:

                    await ws.send("ping")

                    last_ping = time.monotonic()



                try:

                    raw = await asyncio.wait_for(ws.recv(), timeout=0.12)

                except asyncio.TimeoutError:

                    if self._wake and self._wake.is_set():

                        self._wake.clear()

                    continue



                if raw == "pong":

                    continue

                try:

                    data = json.loads(raw)

                except (TypeError, json.JSONDecodeError):

                    continue

                if not isinstance(data, dict):

                    continue

                self._apply_message(data)



    def _apply_message(self, data: dict) -> None:

        typ = data.get("type")

        if typ == "status":

            self.connected = bool(data.get("connected"))

            self._status(

                "live connected" if self.connected else "live disconnected"

            )

            return

        changed = False

        if typ == "state" and isinstance(data.get("bosses"), dict):

            for bid, entry in data["bosses"].items():

                if not isinstance(entry, dict):

                    continue

                key = str(bid)

                merged = merge_boss_entry(self._bosses.get(key), entry)

                if merged != self._bosses.get(key):

                    self._bosses[key] = merged

                    changed = True

            if changed:

                self._emit()

            return

        if typ == "boss" and data.get("boss") is not None and isinstance(

            data.get("entry"), dict

        ):

            bid = str(data["boss"])

            merged = merge_boss_entry(self._bosses.get(bid), data["entry"])

            if merged != self._bosses.get(bid):

                self._bosses[bid] = merged

                self._emit()





def faction_follow_ids(faction: str = "elyos") -> list[str]:

    from .a2tools_feed import load_field_map



    out: list[str] = []

    for fid, meta in load_field_map().items():

        side = (meta.get("side") or "").lower()

        if faction == "elyos" and side == "asmodian":

            continue

        if faction == "asmodian" and side == "elyos":

            continue

        if str(fid).isdigit():

            out.append(str(fid))

    out.sort()

    return out[:MAX_FOLLOW]


