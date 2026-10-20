# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onefile — un solo .exe portable (extrae a temp al arrancar)

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None
ROOT = Path(SPECPATH)

datas = collect_data_files("pinalo_boss_tracker")
data_dir = ROOT / "pinalo_boss_tracker" / "data"
if data_dir.is_dir():
    datas.append((str(data_dir), "pinalo_boss_tracker/data"))

pside_datas, pside_binaries, pside_hidden = collect_all("PySide6")
ws_datas, ws_binaries, ws_hidden = collect_all("websockets")

# QtWebEngine hincha el exe y suele fallar en onefile; el tab web ya tiene fallback
_skip = ("QtWebEngine", "Qt6WebEngine", "webengine")


def _keep(path_or_name) -> bool:
    s = str(path_or_name[0] if isinstance(path_or_name, (tuple, list)) else path_or_name)
    return not any(x.lower() in s.lower() for x in _skip)


pside_datas = [x for x in pside_datas if _keep(x)]
pside_binaries = [x for x in pside_binaries if _keep(x)]

a = Analysis(
    ["launch.py"],
    pathex=[str(ROOT)],
    binaries=pside_binaries + ws_binaries,
    datas=datas + pside_datas + ws_datas,
    hiddenimports=list(pside_hidden)
    + list(ws_hidden)
    + [
        "websockets",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "pinalo_boss_tracker",
        "pinalo_boss_tracker.ui.main_window",
        "pinalo_boss_tracker.sources.a2tools_live",
        "tzdata",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "matplotlib",
        "numpy",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_icon = ROOT / "pinalo_boss_tracker" / "data" / "app_icon.ico"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ValkyriumBossTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_icon) if _icon.is_file() else None,
)
