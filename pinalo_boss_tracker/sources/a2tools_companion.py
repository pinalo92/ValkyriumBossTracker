"""Al arrancar Valkyrium: ajustar A2Tools DPS meter (sin overlay Event Timers).

- Medidor DPS visible (showMeter)
- Plugin Event Timers desactivado (pins/overlay de A2Tools ocultos)
- GS + poder de combate junto a los nombres
- Título ventana → Valkyrium DPS Meter
- Sin icono en la barra de tareas (solo overlay del meter)
- Lanza A2Tools si está instalado y no corre; reinicia si hay que aplicar prefs
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SW_HIDE = 0
SW_SHOWNA = 8  # show without activating

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


def _window_long_fns():
    import ctypes

    user32 = ctypes.windll.user32
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        get_long = user32.GetWindowLongPtrW
        set_long = user32.SetWindowLongPtrW
    else:
        get_long = user32.GetWindowLongW
        set_long = user32.SetWindowLongW
    return user32, get_long, set_long


def _is_main_meter_title(title: str) -> bool:
    low = (title or "").strip().lower()
    return low in ("a2tools dps meter", METER_WINDOW_TITLE.lower())


def _iter_meter_hwnds():
    """HWND visibles del proceso A2Tools con título de medidor principal."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return

    user32 = ctypes.windll.user32
    pids = _meter_pids()
    if not pids:
        return

    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
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
        if not _is_main_meter_title(buf.value or ""):
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = int(rect.right - rect.left)
        h = int(rect.bottom - rect.top)
        if w >= 120 and h >= 40:
            found.append(int(hwnd))
        return True

    user32.EnumWindows(_cb, 0)
    yield from found


def rename_meter_window(title: str = METER_WINDOW_TITLE) -> int:
    """Cambia el título de la ventana del medidor."""
    try:
        import ctypes
    except ImportError:
        return 0

    user32 = ctypes.windll.user32
    renamed = 0
    for hwnd in _iter_meter_hwnds():
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        cur = (buf.value or "").strip()
        if cur.lower() == "a2tools dps meter":
            if user32.SetWindowTextW(hwnd, title):
                renamed += 1
        elif cur.lower() == title.lower():
            renamed += 1
    return renamed


def hide_meter_from_taskbar() -> int:
    """Quita el icono de la barra de tareas (WS_EX_TOOLWINDOW). El meter sigue visible."""
    try:
        import ctypes
    except ImportError:
        return 0

    user32, get_long, set_long = _window_long_fns()
    touched = 0
    for hwnd in _iter_meter_hwnds():
        try:
            ex = int(get_long(hwnd, GWL_EXSTYLE))
        except (OSError, ValueError, OverflowError):
            continue
        new_ex = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        if new_ex == ex:
            touched += 1
            continue
        try:
            set_long(hwnd, GWL_EXSTYLE, new_ex)
        except (OSError, ValueError, OverflowError):
            continue
        # Refrescar entrada de la barra de tareas sin robar foco
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.ShowWindow(hwnd, SW_SHOWNA)
        touched += 1
    return touched


def polish_meter_window_retry(
    title: str = METER_WINDOW_TITLE,
    attempts: int = 10,
    delay_s: float = 0.4,
) -> tuple[int, int]:
    """Renombra + saca de la barra de tareas (reintenta mientras arranca)."""
    renamed = hidden = 0
    for i in range(max(1, attempts)):
        renamed = rename_meter_window(title)
        hidden = hide_meter_from_taskbar()
        if renamed > 0 and hidden > 0:
            return renamed, hidden
        if i + 1 < attempts:
            time.sleep(delay_s)
    return renamed, hidden


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

    renamed, hidden = polish_meter_window_retry()
    bits = ["Event Timers off"]
    if renamed:
        bits.append("título Valkyrium")
    if hidden:
        bits.append("sin barra de tareas")
    return f"{METER_WINDOW_TITLE}: ok ({', '.join(bits)})"
