from __future__ import annotations

import json
import sqlite3
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import AppSettings, BossObservation, Reliability, utcnow
from .paths import app_dir, db_path

# Compat: tests / imports antiguos
APP_DIR = app_dir()
DB_PATH = db_path()


def _connect() -> sqlite3.Connection:
    d = app_dir()
    d.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = _connect()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS observations (
          boss_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          reliability TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          killed_at TEXT,
          predicted_ready_at TEXT,
          predicted_window_end TEXT,
          note TEXT
        );
        CREATE TABLE IF NOT EXISTS history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT NOT NULL,
          event TEXT NOT NULL,
          boss_id TEXT,
          detail TEXT
        );
        CREATE TABLE IF NOT EXISTS tp_numbers (
          tp_id TEXT PRIMARY KEY,
          map_number INTEGER NOT NULL
        );
        """
    )
    cols = {r[1] for r in con.execute("PRAGMA table_info(observations)").fetchall()}
    if "hp" not in cols:
        con.execute("ALTER TABLE observations ADD COLUMN hp INTEGER")
    if con.execute("SELECT 1 FROM settings WHERE id=1").fetchone() is None:
        con.execute(
            "INSERT INTO settings(id, json) VALUES (1, ?)",
            (json.dumps(AppSettings().__dict__),),
        )
    con.commit()
    con.close()


def load_settings() -> AppSettings:
    init_db()
    con = _connect()
    row = con.execute("SELECT json FROM settings WHERE id=1").fetchone()
    con.close()
    data = json.loads(row["json"])
    allowed = {f.name for f in fields(AppSettings)}
    filtered = {k: v for k, v in data.items() if k in allowed}
    s = AppSettings(**filtered)
    if not (s.server or "").strip():
        s.server = "Kaisinel"
    return s


def save_settings(s: AppSettings) -> None:
    init_db()
    con = _connect()
    con.execute(
        "UPDATE settings SET json=? WHERE id=1",
        (json.dumps(s.__dict__),),
    )
    con.commit()
    con.close()


def _parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_observations() -> dict[str, BossObservation]:
    init_db()
    con = _connect()
    rows = con.execute("SELECT * FROM observations").fetchall()
    con.close()
    out = {}
    for r in rows:
        hp = r["hp"] if "hp" in r.keys() else None
        out[r["boss_id"]] = BossObservation(
            boss_id=r["boss_id"],
            source=r["source"],
            reliability=Reliability(r["reliability"]),
            updated_at=_parse_dt(r["updated_at"]) or utcnow(),
            killed_at=_parse_dt(r["killed_at"]),
            predicted_ready_at=_parse_dt(r["predicted_ready_at"]),
            predicted_window_end=_parse_dt(r["predicted_window_end"]),
            note=r["note"] or "",
            hp=int(hp) if hp is not None else None,
        )
    return out


def upsert_observation(obs: BossObservation) -> None:
    init_db()
    con = _connect()
    con.execute(
        """
        INSERT INTO observations(
          boss_id, source, reliability, updated_at, killed_at,
          predicted_ready_at, predicted_window_end, note, hp
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(boss_id) DO UPDATE SET
          source=excluded.source,
          reliability=excluded.reliability,
          updated_at=excluded.updated_at,
          killed_at=excluded.killed_at,
          predicted_ready_at=excluded.predicted_ready_at,
          predicted_window_end=excluded.predicted_window_end,
          note=excluded.note,
          hp=excluded.hp
        """,
        (
            obs.boss_id,
            obs.source,
            obs.reliability.value,
            obs.updated_at.isoformat(),
            obs.killed_at.isoformat() if obs.killed_at else None,
            obs.predicted_ready_at.isoformat() if obs.predicted_ready_at else None,
            obs.predicted_window_end.isoformat() if obs.predicted_window_end else None,
            obs.note,
            obs.hp,
        ),
    )
    con.commit()
    con.close()


def add_history(event: str, boss_id: Optional[str] = None, detail: str = "") -> None:
    init_db()
    con = _connect()
    con.execute(
        "INSERT INTO history(ts, event, boss_id, detail) VALUES (?,?,?,?)",
        (utcnow().isoformat(), event, boss_id, detail),
    )
    con.commit()
    con.close()


def recent_history(limit: int = 50) -> list[dict]:
    init_db()
    con = _connect()
    rows = con.execute(
        "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def kills_today(limit: int = 40) -> list[dict]:
    """Kills del día local (eventos kill / killed)."""
    from datetime import datetime, timezone

    init_db()
    today = datetime.now().astimezone().date().isoformat()
    con = _connect()
    rows = con.execute(
        """
        SELECT * FROM history
        WHERE event IN ('kill','killed')
        ORDER BY id DESC LIMIT ?
        """,
        (limit * 3,),
    ).fetchall()
    con.close()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        ts = d.get("ts") or ""
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone().date().isoformat() != today:
                continue
        except ValueError:
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return out


def load_tp_numbers() -> dict[str, int]:
    init_db()
    con = _connect()
    rows = con.execute("SELECT tp_id, map_number FROM tp_numbers").fetchall()
    con.close()
    return {r["tp_id"]: int(r["map_number"]) for r in rows}


def save_tp_number(tp_id: str, map_number: int) -> None:
    init_db()
    con = _connect()
    con.execute(
        """
        INSERT INTO tp_numbers(tp_id, map_number) VALUES (?,?)
        ON CONFLICT(tp_id) DO UPDATE SET map_number=excluded.map_number
        """,
        (tp_id, int(map_number)),
    )
    con.commit()
    con.close()


def save_tp_numbers_bulk(mapping: dict[str, int]) -> None:
    init_db()
    con = _connect()
    for tp_id, num in mapping.items():
        con.execute(
            """
            INSERT INTO tp_numbers(tp_id, map_number) VALUES (?,?)
            ON CONFLICT(tp_id) DO UPDATE SET map_number=excluded.map_number
            """,
            (tp_id, int(num)),
        )
    con.commit()
    con.close()
