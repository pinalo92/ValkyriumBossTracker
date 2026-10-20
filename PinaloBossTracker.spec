# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec — portable onedir con datos + caras + websockets



from pathlib import Path



from PyInstaller.utils.hooks import collect_all, collect_data_files



block_cipher = None

ROOT = Path(SPECPATH)



datas = collect_data_files("pinalo_boss_tracker")

# Asegurar carpeta data completa (JSON + faces/*.webp)

data_dir = ROOT / "pinalo_boss_tracker" / "data"

if data_dir.is_dir():

    datas.append((str(data_dir), "pinalo_boss_tracker/data"))



pside_datas, pside_binaries, pside_hidden = collect_all("PySide6")

ws_datas, ws_binaries, ws_hidden = collect_all("websockets")



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

    excludes=["pytest", "matplotlib", "numpy"],

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
    [],
    exclude_binaries=True,
    name="PinaloBossTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_icon) if _icon.is_file() else None,
)



coll = COLLECT(

    exe,

    a.binaries,

    a.zipfiles,

    a.datas,

    strip=False,

    upx=False,

    upx_exclude=[],

    name="PinaloBossTracker",

)


