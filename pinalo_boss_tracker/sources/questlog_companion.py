"""Al arrancar Valkyrium: abrir Questlog Desktop (DPS / overlays).

Si no está instalado, descarga el instalador oficial desde cdn.questlog.gg
y lo ejecuta (no se embebe en el EXE: ~111 MB y se actualiza solo).

Questlog se actualiza sola (descarga en segundo plano e instala al reiniciar).
Si hay un instalador pendiente en el updater, reiniciamos Questlog para aplicarlo.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .. import __version__

QUESTLOG_PROCESS = "Questlog.exe"
QUESTLOG_LAUNCHER = "questlog-launcher.exe"
UPDATER_PENDING = (
    Path.home() / "AppData" / "Local" / "@questlogdesktop-app-updater" / "pending"
)

APP_PAGE_URLS = (
    "https://questlog.gg/aion-2/es/app",
    "https://questlog.gg/aion-2/app",
)
SETUP_URL_RE = re.compile(
    r"https://cdn\.questlog\.gg/desktop/questlog-setup-[\d.]+\.exe",
    re.IGNORECASE,
)
# Fallback si la página cambia de formato (se sustituye al resolver URL).
FALLBACK_SETUP_URL = "https://cdn.questlog.gg/desktop/questlog-setup-0.1.37.exe"
MIN_SETUP_BYTES = 20_000_000  # ~111 MB; rechazar HTML/error pequeño
UA = f"ValkyriumBossTracker/{__version__}"

ProgressCb = Optional[Callable[[str], None]]


def _exe_candidates() -> list[Path]:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = Path.home() / "AppData" / "Local"
    return [
        Path(pf) / "Questlog" / QUESTLOG_PROCESS,
        Path(pf86) / "Questlog" / QUESTLOG_PROCESS,
        local / "Programs" / "Questlog" / QUESTLOG_PROCESS,
        local / "Questlog" / QUESTLOG_PROCESS,
    ]


def find_questlog_exe() -> Optional[Path]:
    for p in _exe_candidates():
        if p.is_file():
            return p
    return None


def _image_running(image: str) -> bool:
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    out = (r.stdout or "").lower()
    return image.lower() in out


def is_questlog_running() -> bool:
    return _image_running(QUESTLOG_PROCESS) or _image_running(QUESTLOG_LAUNCHER)


def has_pending_update() -> bool:
    """True si electron-updater dejó un setup pendiente (p.ej. questlog-setup-*.exe)."""
    if not UPDATER_PENDING.is_dir():
        return False
    try:
        for p in UPDATER_PENDING.iterdir():
            name = p.name.lower()
            if p.is_file() and name.endswith(".exe") and "setup" in name:
                return True
            if p.is_file() and name == "update-info.json":
                return True
    except OSError:
        return False
    return False


def stop_questlog(timeout_s: float = 10.0) -> None:
    """Cierra Questlog (proceso principal + launcher)."""
    if not is_questlog_running():
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for image in (QUESTLOG_PROCESS, QUESTLOG_LAUNCHER):
        if _image_running(image):
            subprocess.run(
                ["taskkill", "/IM", image, "/F"],
                capture_output=True,
                timeout=10,
                creationflags=flags,
            )
    deadline = time.time() + timeout_s
    while time.time() < deadline and is_questlog_running():
        time.sleep(0.25)


def launch_questlog(exe: Optional[Path] = None) -> bool:
    path = exe or find_questlog_exe()
    if not path:
        return False
    try:
        subprocess.Popen(
            [str(path)],
            cwd=str(path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return True


def resolve_setup_url() -> str:
    """Lee la URL del instalador desde la web de Questlog (versión actual)."""
    for page in APP_PAGE_URLS:
        try:
            req = urllib.request.Request(page, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        # Preferir la forma sin escape JSON
        m = SETUP_URL_RE.search(html.replace(r"\/", "/"))
        if m:
            return m.group(0)
    return FALLBACK_SETUP_URL


def _download(url: str, dest: Path, timeout: float = 600.0, progress: ProgressCb = None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_pct = -1
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress and total > 0:
                pct = min(99, int(100 * done / total))
                if pct != last_pct and pct % 5 == 0:
                    last_pct = pct
                    mb = done / (1024 * 1024)
                    progress(f"Descargando Questlog… {pct}% ({mb:.0f} MB)")
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)


def download_questlog_setup(
    dest: Optional[Path] = None,
    progress: ProgressCb = None,
) -> Path:
    """Descarga el instalador oficial a TEMP (o dest)."""
    if dest is None:
        dest = Path(tempfile.gettempdir()) / "Valkyrium" / "questlog-setup.exe"
    if progress:
        progress("Buscando instalador de Questlog…")
    url = resolve_setup_url()
    if progress:
        progress(f"Descargando Questlog… (~111 MB)")
    _download(url, dest, progress=progress)
    size = dest.stat().st_size if dest.is_file() else 0
    if size < MIN_SETUP_BYTES:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Descarga de Questlog inválida ({size} bytes). Prueba de nuevo o instala desde questlog.gg"
        )
    return dest


def run_questlog_installer(setup: Path, silent: bool = False) -> bool:
    """Lanza el instalador (UAC). silent=/S de NSIS si el build lo soporta."""
    if not setup.is_file():
        return False
    params = "/S" if silent else ""
    try:
        import ctypes

        # runas → UAC; >32 = ok (ShellExecute)
        rc = int(
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                str(setup),
                params,
                str(setup.parent),
                1,
            )
        )
        if rc > 32:
            return True
    except (OSError, AttributeError, ValueError):
        pass
    try:
        args = [str(setup)]
        if silent:
            args.append("/S")
        subprocess.Popen(
            args,
            cwd=str(setup.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        return False


def wait_for_questlog_install(
    timeout_s: float = 600.0,
    progress: ProgressCb = None,
) -> Optional[Path]:
    """Espera a que aparezca Questlog.exe tras el instalador."""
    deadline = time.time() + timeout_s
    last_msg = 0.0
    while time.time() < deadline:
        exe = find_questlog_exe()
        if exe:
            return exe
        now = time.time()
        if progress and now - last_msg > 8:
            last_msg = now
            progress("Esperando a que termine la instalación de Questlog…")
        time.sleep(2.0)
    return None


def install_questlog_if_missing(
    progress: ProgressCb = None,
    silent_installer: bool = False,
) -> tuple[Optional[Path], str]:
    """
    Si no hay Questlog, descarga el setup oficial y lo ejecuta.
    Devuelve (exe|None, mensaje).
    """
    exe = find_questlog_exe()
    if exe:
        return exe, "ya instalado"

    try:
        setup = download_questlog_setup(progress=progress)
    except Exception as e:
        return None, f"No se pudo descargar Questlog: {e}"

    if progress:
        progress("Instalando Questlog (acepta el UAC si aparece)…")
    if not run_questlog_installer(setup, silent=silent_installer):
        return None, "No se pudo lanzar el instalador de Questlog"

    exe = wait_for_questlog_install(progress=progress)
    if not exe:
        return (
            None,
            "Instalador lanzado. Cuando termine, reinicia Valkyrium o abre Questlog a mano. "
            "También necesitas Npcap (npcap.com) si aún no lo tienes.",
        )
    return exe, "Questlog instalado"


def ensure_questlog_on_startup(
    auto_install: bool = True,
    progress: ProgressCb = None,
) -> str:
    """
    Abre Questlog si hace falta. Si no está instalado y auto_install, lo descarga.
    Si hay update pendiente, reinicia para instalarla.
    """
    freshly_installed = False
    exe = find_questlog_exe()
    if not exe:
        if not auto_install:
            return "Questlog no instalado (opcional — questlog.gg/aion-2/app)"
        exe, note = install_questlog_if_missing(progress=progress)
        if not exe:
            return note
        freshly_installed = True

    pending = has_pending_update()
    running = is_questlog_running()

    if pending and running:
        stop_questlog()
        running = False

    if not running:
        if not launch_questlog(exe):
            return "Questlog: no se pudo abrir"
        time.sleep(1.2)
        if freshly_installed:
            return (
                "Questlog: instalado y abierto "
                "(si no ves DPS, instala Npcap desde npcap.com)"
            )
        if pending:
            return "Questlog: abierto (aplicando actualización pendiente)"
        return "Questlog: abierto"

    if freshly_installed:
        return "Questlog: instalado"
    return "Questlog: ya estaba abierto"
