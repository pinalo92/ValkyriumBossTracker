"""Suma el combate en curso y prepara las filas del medidor."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


IDLE_RESET_S = 12.0


def format_number(value: float) -> str:
    n = int(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.2f}M".replace(".", ",")
    if n >= 10_000:
        return f"{sign}{n / 1000:.1f}k".replace(".", ",")
    return f"{sign}{n:,}".replace(",", ".")


def format_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


@dataclass
class MeterRow:
    name: str
    damage: int
    dps: float
    pct: float
    you: bool


@dataclass
class MeterView:
    fighting: bool
    elapsed_s: float
    rows: list[MeterRow]
    your_dps: float
    total_damage: int
    status: str
    listening: bool


@dataclass
class _Actor:
    damage: int = 0
    heal: int = 0
    name: str = ""
    you: bool = False


@dataclass
class CombatSession:
    status: str = "Buscando Npcap…"
    listening: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _actors: dict[int, _Actor] = field(default_factory=dict)
    _started: float | None = None
    _last_hit: float | None = None

    def set_status(self, text: str, *, listening: bool | None = None) -> None:
        with self._lock:
            self.status = text
            if listening is not None:
                self.listening = listening

    def rename(self, entity_id: int, name: str, you: bool) -> None:
        name = (name or "").strip()
        if not name:
            return
        with self._lock:
            actor = self._actors.setdefault(entity_id, _Actor())
            actor.name = name
            if you:
                actor.you = True

    def add_hit(self, actor_id: int, target_id: int, damage: int, heal: int) -> None:
        if damage <= 0 and heal <= 0:
            return
        now = time.monotonic()
        with self._lock:
            if self._last_hit is not None and now - self._last_hit > IDLE_RESET_S:
                self._actors = {
                    eid: _Actor(name=a.name, you=a.you) for eid, a in self._actors.items() if a.name or a.you
                }
                self._started = None
            if self._started is None and damage > 0:
                self._started = now
            self._last_hit = now
            actor = self._actors.setdefault(actor_id, _Actor())
            actor.damage += max(0, int(damage))
            actor.heal += max(0, int(heal))
            _ = target_id

    def reset_fight(self) -> None:
        with self._lock:
            self._actors = {
                eid: _Actor(name=a.name, you=a.you) for eid, a in self._actors.items() if a.name or a.you
            }
            self._started = None
            self._last_hit = None

    def snapshot(self, limit: int = 8) -> MeterView:
        now = time.monotonic()
        with self._lock:
            if self._last_hit is not None and now - self._last_hit > IDLE_RESET_S and self._started is not None:
                self._actors = {
                    eid: _Actor(name=a.name, you=a.you) for eid, a in self._actors.items() if a.name or a.you
                }
                self._started = None
                self._last_hit = None
            elapsed = 0.0 if self._started is None else max(0.1, now - self._started)
            fighting = self._started is not None
            ranked = [a for a in self._actors.values() if a.damage > 0]
            ranked.sort(key=lambda a: a.damage, reverse=True)
            total = sum(a.damage for a in ranked)
            your = next((a for a in self._actors.values() if a.you), None)
            rows: list[MeterRow] = []
            for actor in ranked[:limit]:
                label = actor.name or "Jugador"
                rows.append(
                    MeterRow(
                        name=label,
                        damage=actor.damage,
                        dps=actor.damage / elapsed if fighting else 0.0,
                        pct=(actor.damage / total * 100.0) if total else 0.0,
                        you=actor.you,
                    )
                )
            your_dps = (your.damage / elapsed) if (your and fighting) else 0.0
            return MeterView(
                fighting=fighting,
                elapsed_s=elapsed if fighting else 0.0,
                rows=rows,
                your_dps=your_dps,
                total_damage=total,
                status=self.status,
                listening=self.listening,
            )
