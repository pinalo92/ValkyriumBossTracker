"""Rutas a datos empaquetados (dev + PyInstaller frozen)."""

from __future__ import annotations

import sys
from pathlib import Path


def package_data_dir() -> Path:
    """Carpeta pinalo_boss_tracker/data (JSON, caras, etc.)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        for cand in (
            meipass / "pinalo_boss_tracker" / "data",
            meipass / "data",
        ):
            if cand.is_dir():
                return cand
    return Path(__file__).resolve().parent / "data"
