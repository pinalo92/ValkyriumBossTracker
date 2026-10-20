"""Comprobación / descarga de actualizaciones del portable."""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import __version__

DEFAULT_MANIFEST_NAME = "update_manifest.json"
# URL estable del manifiesto en GitHub (se rellena al publicar el repo).
# Formato: https://raw.githubusercontent.com/USER/REPO/main/update_manifest.json
DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/pinalo92/ValkyriumBossTracker/main/update_manifest.json"
)


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str = ""
    current: str = __version__

    @property
    def available(self) -> bool:
        return _version_tuple(self.version) > _version_tuple(self.current)


def _version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in (v or "0").strip().lstrip("vV").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts or (0,))


def manifest_path(app_root: Path) -> Path:
    return app_root / DEFAULT_MANIFEST_NAME


def resolve_manifest_url(app_root: Path, configured: str = "") -> str:
    if (configured or "").strip():
        return configured.strip()
    local = manifest_path(app_root)
    if local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            # Preferir pointer a manifiesto remoto; no usar "url" del zip local
            remote = str(data.get("manifest_url") or "").strip()
            if remote:
                return remote
        except (OSError, json.JSONDecodeError):
            pass
    return (DEFAULT_MANIFEST_URL or "").strip()


def check_update(manifest_url: str, current: str = __version__) -> Optional[UpdateInfo]:
    """Lee un JSON remoto: {version, url, notes?}."""
    url = (manifest_url or "").strip()
    if not url:
        return None
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"PinaloBossTracker/{current}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"No se pudo leer el manifiesto: {e}") from e
    ver = str(data.get("version") or "").strip()
    zip_url = str(data.get("url") or data.get("zip") or "").strip()
    if not ver or not zip_url:
        raise RuntimeError("Manifiesto incompleto (faltan version/url)")
    return UpdateInfo(
        version=ver,
        url=zip_url,
        notes=str(data.get("notes") or ""),
        current=current,
    )


def apply_zip_update(zip_url: str, portable_root: Path) -> Path:
    """
    Descarga el zip, extrae a carpeta hermana *_new y deja Actualizar_y_Reiniciar.bat
    para sustituir la carpeta actual al salir.
    """
    portable_root = portable_root.resolve()
    parent = portable_root.parent
    staging = parent / f"{portable_root.name}_update_staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(
        zip_url,
        headers={"User-Agent": f"PinaloBossTracker/{__version__}"},
    )
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(tmp_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(staging)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Si el zip trae una sola carpeta raíz, usarla
    kids = [p for p in staging.iterdir() if p.name not in ("__MACOSX",)]
    source = kids[0] if len(kids) == 1 and kids[0].is_dir() else staging

    bat = portable_root / "Actualizar_y_Reiniciar.bat"
    bat.write_text(
        "\r\n".join(
            [
                "@echo off",
                "cd /d \"%~dp0\"",
                "echo Actualizando Pinalo Boss Tracker...",
                "timeout /t 2 /nobreak >nul",
                f'robocopy "{source}" "%~dp0." /e /xo /r:2 /w:1 >nul',
                "start \"\" \"%~dp0Iniciar_Portable.bat\"",
                "del \"%~f0\"",
            ]
        )
        + "\r\n",
        encoding="ascii",
        errors="ignore",
    )
    return bat
