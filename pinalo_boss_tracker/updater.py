"""Comprobación / descarga de actualizaciones (zip carpeta o EXE onefile)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import __version__

DEFAULT_MANIFEST_NAME = "update_manifest.json"
DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/pinalo92/ValkyriumBossTracker/master/update_manifest.json"
)


@dataclass
class UpdateInfo:
    version: str
    url: str = ""  # zip carpeta portable
    exe_url: str = ""  # EXE onefile
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


def is_onefile_build() -> bool:
    """True si es el ValkyriumBossTracker.exe suelto (sin carpeta _internal)."""
    if not getattr(sys, "frozen", False):
        return False
    exe = Path(sys.executable).resolve()
    if (exe.parent / "_internal").is_dir():
        return False
    # onedir antiguo: PinaloBossTracker.exe + _internal
    return True


def manifest_path(app_root: Path) -> Path:
    return app_root / DEFAULT_MANIFEST_NAME


def resolve_manifest_url(app_root: Path, configured: str = "") -> str:
    if (configured or "").strip():
        return configured.strip()
    local = manifest_path(app_root)
    if local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            remote = str(data.get("manifest_url") or "").strip()
            if remote:
                return remote
        except (OSError, json.JSONDecodeError):
            pass
    return (DEFAULT_MANIFEST_URL or "").strip()


def check_update(manifest_url: str, current: str = __version__) -> Optional[UpdateInfo]:
    """Lee JSON remoto: {version, url?, exe_url?, notes?}."""
    url = (manifest_url or "").strip()
    if not url:
        return None
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"ValkyriumBossTracker/{current}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"No se pudo leer el manifiesto: {e}") from e
    ver = str(data.get("version") or "").strip()
    zip_url = str(data.get("url") or data.get("zip") or "").strip()
    exe_url = str(data.get("exe_url") or data.get("exe") or "").strip()
    if not ver or (not zip_url and not exe_url):
        raise RuntimeError("Manifiesto incompleto (faltan version y url/exe_url)")
    return UpdateInfo(
        version=ver,
        url=zip_url,
        exe_url=exe_url,
        notes=str(data.get("notes") or ""),
        current=current,
    )


def _download(url: str, dest: Path, timeout: float = 180.0) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"ValkyriumBossTracker/{__version__}"},
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def apply_exe_update(exe_url: str, current_exe: Path) -> Path:
    """
    Descarga el nuevo .exe junto al actual y deja un .bat que lo sustituye al salir.
    """
    current_exe = current_exe.resolve()
    folder = current_exe.parent
    new_path = folder / f"{current_exe.stem}.new.exe"
    bak_path = folder / f"{current_exe.stem}.bak.exe"
    if new_path.exists():
        new_path.unlink()
    _download(exe_url, new_path)
    if new_path.stat().st_size < 1_000_000:
        new_path.unlink(missing_ok=True)
        raise RuntimeError("Descarga del EXE demasiado pequeña / corrupta")

    pid = os.getpid()
    bat = folder / "Actualizar_y_Reiniciar.bat"
    # Esperar a que muera el proceso, renombrar, arrancar
    lines = [
        "@echo off",
        "setlocal",
        f'cd /d "{folder}"',
        "echo Actualizando Valkyrium...",
        f":waitloop",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto waitloop",
        ")",
        "timeout /t 1 /nobreak >nul",
        f'if exist "{bak_path.name}" del /f /q "{bak_path.name}"',
        f'rename "{current_exe.name}" "{bak_path.name}"',
        f'rename "{new_path.name}" "{current_exe.name}"',
        f'start "" "{current_exe.name}"',
        "timeout /t 2 /nobreak >nul",
        f'if exist "{bak_path.name}" del /f /q "{bak_path.name}"',
        'del "%~f0"',
    ]
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", errors="ignore")
    return bat


def apply_zip_update(zip_url: str, portable_root: Path) -> Path:
    """
    Descarga el zip, extrae a staging y deja Actualizar_y_Reiniciar.bat
    para sustituir la carpeta portable al salir.
    """
    portable_root = portable_root.resolve()
    parent = portable_root.parent
    staging = parent / f"{portable_root.name}_update_staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    tmp_path = Path(tempfile.mktemp(suffix=".zip"))
    try:
        _download(zip_url, tmp_path)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(staging)
    finally:
        tmp_path.unlink(missing_ok=True)

    kids = [p for p in staging.iterdir() if p.name not in ("__MACOSX",)]
    source = kids[0] if len(kids) == 1 and kids[0].is_dir() else staging

    bat = portable_root / "Actualizar_y_Reiniciar.bat"
    starter = "Iniciar_Portable.bat"
    if not (portable_root / starter).exists():
        starter = "PinaloBossTracker.exe"
        if (portable_root / "ValkyriumBossTracker.exe").exists():
            starter = "ValkyriumBossTracker.exe"
    bat.write_text(
        "\r\n".join(
            [
                "@echo off",
                "cd /d \"%~dp0\"",
                "echo Actualizando Valkyrium...",
                "timeout /t 2 /nobreak >nul",
                f'robocopy "{source}" "%~dp0." /e /xo /r:2 /w:1 >nul',
                f'start "" "%~dp0{starter}"',
                "del \"%~f0\"",
            ]
        )
        + "\r\n",
        encoding="ascii",
        errors="ignore",
    )
    return bat
