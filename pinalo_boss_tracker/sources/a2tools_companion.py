"""Al arrancar Valkyrium: ajustar A2Tools DPS meter (sin overlay Event Timers).

- Medidor DPS visible (showMeter)
- Plugin Event Timers desactivado (pins/overlay de A2Tools ocultos)
- GS + poder de combate junto a los nombres
- Título ventana → Valkyrium DPS Meter
- Oculta el engranaje de Ajustes (tapa Win32 sobre la esquina del meter)
- Lanza A2Tools si está instalado y no corre; reinicia si hay que aplicar prefs
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

A2_ROAMING = Path.home() / "AppData" / "Roaming" / "com.a2tools.dps-meter"
A2_SETTINGS = A2_ROAMING / "settings.json"
A2_PROCESS = "a2tools-dps-meter.exe"
# Título cosmético de la ventana (por debajo sigue siendo A2Tools).
METER_WINDOW_TITLE = "Valkyrium DPS Meter"

# Prefs fijas: Valkyrium ya cubre bosses; A2Tools solo combate.
PREFERRED: dict[str, str] = {
    "dpsMeter.showMeter": "true",
    "dpsMeter.partyStat": "both",
    "dpsMeter.autoHideMeter": "false",
    "dpsMeter.pluginsDisabled": '["event-timers"]',
    "dpsMeter.pluginWindows": '{"event-timers":"hidden"}',
}

# Geometría tapa engranaje (esquina superior derecha del meter).
GEAR_COVER_W = 34
GEAR_COVER_H = 30
GEAR_COVER_MARGIN_R = 6
GEAR_COVER_MARGIN_T = 4
GEAR_COVER_COLOR = "#16181d"


def _exe_candidates() -> list[Path]:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = Path.home() / "AppData" / "Local"
    return [
        Path(pf) / "A2Tools DPS Meter" / A2_PROCESS,
        Path(pf86) / "A2Tools DPS Meter" / A2_PROCESS,
        local / "Programs" / "A2Tools DPS Meter" / A2_PROCESS,
    ]


def find_a2tools_exe() -> Optional[Path]:
    for p in _exe_candidates():
        if p.is_file():
            return p
    return None


def is_a2tools_running() -> bool:
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {A2_PROCESS}", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    out = (r.stdout or "").lower()
    return A2_PROCESS.lower() in out


def apply_preferred_settings() -> bool:
    """Escribe prefs Valkyrium. True si cambió algo."""
    data: dict = {}
    if A2_SETTINGS.is_file():
        try:
            raw = json.loads(A2_SETTINGS.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            data = {}
    changed = False
    for key, want in PREFERRED.items():
        cur = data.get(key)
        if key in ("dpsMeter.pluginsDisabled", "dpsMeter.pluginWindows"):
            try:
                same = json.loads(str(cur or "")) == json.loads(want)
            except (TypeError, json.JSONDecodeError):
                same = str(cur) == want
            if same:
                continue
        elif str(cur) == want:
            continue
        data[key] = want
        changed = True
    if not changed and A2_SETTINGS.is_file():
        return False
    A2_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    A2_SETTINGS.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def _stop_a2tools(timeout_s: float = 8.0) -> None:
    if not is_a2tools_running():
        return
    subprocess.run(
        ["taskkill", "/IM", A2_PROCESS, "/F"],
        capture_output=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline and is_a2tools_running():
        time.sleep(0.25)


def launch_a2tools(exe: Optional[Path] = None) -> bool:
    path = exe or find_a2tools_exe()
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


def _meter_pids() -> set[int]:
    pids: set[int] = set()
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {A2_PROCESS}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in (r.stdout or "").splitlines():
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == A2_PROCESS.lower():
                try:
                    pids.add(int(parts[1]))
                except ValueError:
                    pass
    except (OSError, subprocess.TimeoutExpired):
        pass
    return pids


def find_meter_hwnd() -> int:
    """HWND de la ventana principal del medidor."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return 0

    user32 = ctypes.windll.user32
    pids = _meter_pids()
    if not pids:
        return 0

    found = 0
    want_titles = {
        METER_WINDOW_TITLE.lower(),
        "a2tools dps meter",
    }

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        nonlocal found
        if found:
            return False
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if (buf.value or "").strip().lower() in want_titles:
            # Preferir ventana con área razonable (no widgets minúsculos)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = int(rect.right - rect.left)
            h = int(rect.bottom - rect.top)
            if w >= 120 and h >= 40:
                found = int(hwnd)
                return False
        return True

    user32.EnumWindows(_cb, 0)
    return found


def rename_meter_window(title: str = METER_WINDOW_TITLE) -> int:
    """Cambia el título de la ventana del medidor (barra de título / Alt-Tab)."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return 0

    user32 = ctypes.windll.user32
    pids = _meter_pids()
    if not pids:
        return 0

    renamed = 0

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        nonlocal renamed
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        cur = (buf.value or "").strip()
        low = cur.lower()
        if low == "a2tools dps meter":
            if user32.SetWindowTextW(hwnd, title):
                renamed += 1
        elif low == title.lower():
            renamed += 1
        return True

    user32.EnumWindows(_cb, 0)
    return renamed


def rename_meter_window_retry(
    title: str = METER_WINDOW_TITLE,
    attempts: int = 8,
    delay_s: float = 0.4,
) -> int:
    total = 0
    for i in range(max(1, attempts)):
        total = rename_meter_window(title)
        if total > 0:
            return total
        if i + 1 < attempts:
            time.sleep(delay_s)
    return total


def meter_window_screen_rect() -> Optional[tuple[int, int, int, int]]:
    """(left, top, right, bottom) pantalla del meter, o None."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    user32 = ctypes.windll.user32
    meter = find_meter_hwnd()
    if not meter or not user32.IsWindowVisible(meter) or user32.IsIconic(meter):
        return None
    rect = wintypes.RECT()
    user32.GetWindowRect(meter, ctypes.byref(rect))
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def gear_cover_screen_pos() -> Optional[tuple[int, int]]:
    """Esquina superior-izquierda de la tapa del engranaje, o None."""
    rect = meter_window_screen_rect()
    if not rect:
        return None
    _l, top, right, _b = rect
    x = right - GEAR_COVER_W - GEAR_COVER_MARGIN_R
    y = top + GEAR_COVER_MARGIN_T
    return x, y


def ensure_a2tools_on_startup() -> str:
    """
    Aplica prefs (meter sí, overlay Event Timers no) y asegura que A2Tools corra.
    Al abrir A2Tools, él mismo comprueba sus actualizaciones.
    """
    exe = find_a2tools_exe()
    if not exe:
        return "A2Tools no instalado (opcional)"

    changed = apply_preferred_settings()
    running = is_a2tools_running()

    if changed and running:
        _stop_a2tools()
        running = False

    if not running:
        if not launch_a2tools(exe):
            return "A2Tools: no se pudo abrir"
        time.sleep(1.0)

    rename_meter_window_retry()
    gear_ok = bool(find_meter_hwnd())
    gear_note = "listo" if gear_ok else "meter cargando"
    return f"{METER_WINDOW_TITLE}: ok ({gear_note}, Event Timers off)"
