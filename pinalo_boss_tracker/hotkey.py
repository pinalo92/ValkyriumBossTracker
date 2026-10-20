"""Atajo global Windows (RegisterHotKey) — no requiere foco en la ventana."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from typing import Callable, Optional

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QCoreApplication

user32 = ctypes.windll.user32

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

# Ctrl+Shift+B — Win+B lo reserva Windows para la bandeja
HOTKEY_ID = 0x5042  # 'PB'
HOTKEY_VK = 0x42  # 'B'
HOTKEY_MODS = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey: Callable[[], None]):
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if isinstance(eventType, QByteArray):
            et = bytes(eventType).decode("utf-8", errors="ignore")
        elif isinstance(eventType, (bytes, bytearray)):
            et = eventType.decode("utf-8", errors="ignore")
        else:
            et = str(eventType)
        if et not in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            return False, 0
        try:
            addr = int(message)
        except (TypeError, ValueError):
            try:
                addr = int(message.__int__())  # type: ignore[attr-defined]
            except Exception:
                return False, 0
        msg = wt.MSG.from_address(addr)
        if msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID:
            self._on_hotkey()
            return True, 0
        return False, 0


class GlobalHotkey:
    """Registra Ctrl+Shift+B a nivel sistema."""

    def __init__(self, callback: Callable[[], None]):
        self._callback = callback
        self._filter: Optional[_HotkeyFilter] = None
        self._registered = False

    def start(self) -> bool:
        if self._registered:
            return True
        ok = bool(user32.RegisterHotKey(None, HOTKEY_ID, HOTKEY_MODS, HOTKEY_VK))
        if not ok:
            return False
        self._filter = _HotkeyFilter(self._callback)
        app = QCoreApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)
        self._registered = True
        return True

    def stop(self) -> None:
        if self._registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False
        app = QCoreApplication.instance()
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
