"""Rutas de datos: AppData normal o carpeta portable junto al exe/script."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def install_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path.cwd())
    # carpeta del proyecto (…/PinaloBossTracker)
    roots.append(Path(__file__).resolve().parents[1])
    # dedupe
    out: list[Path] = []
    seen: set[Path] = set()
    for r in roots:
        try:
            key = r.resolve()
        except OSError:
            key = r
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def is_portable() -> bool:
    if os.environ.get("PINALO_PORTABLE", "").strip() in ("1", "true", "yes"):
        return True
    if os.environ.get("PINALO_DATA_DIR", "").strip():
        return True
    for root in install_roots():
        if (root / "portable.txt").exists() or (root / "PINALO_PORTABLE").exists():
            return True
    return False


def resolve_app_dir() -> Path:
    explicit = os.environ.get("PINALO_DATA_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if is_portable():
        for root in install_roots():
            if (root / "portable.txt").exists() or (root / "PINALO_PORTABLE").exists():
                return (root / "data").resolve()
            if os.environ.get("PINALO_PORTABLE", "").strip() in ("1", "true", "yes"):
                return (root / "data").resolve()
        return (install_roots()[0] / "data").resolve()
    return Path.home() / "AppData" / "Local" / "PinaloBossTracker"


_app_dir: Path | None = None


def app_dir() -> Path:
    global _app_dir
    if _app_dir is None:
        _app_dir = resolve_app_dir()
        _app_dir.mkdir(parents=True, exist_ok=True)
        _maybe_migrate_from_appdata(_app_dir)
    return _app_dir


def _maybe_migrate_from_appdata(dest: Path) -> None:
    """Si portable/data está vacío y hay DB en AppData, la copia una vez."""
    dest_db = dest / "tracker.db"
    if dest_db.exists():
        return
    legacy = Path.home() / "AppData" / "Local" / "PinaloBossTracker" / "tracker.db"
    if not legacy.exists():
        return
    try:
        import shutil

        shutil.copy2(legacy, dest_db)
    except OSError:
        pass


def db_path() -> Path:
    return app_dir() / "tracker.db"
