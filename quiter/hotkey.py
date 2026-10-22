"""Global Ctrl+Shift+E hotkey via Win32 RegisterHotKey.

RegisterHotKey keeps its own message queue and needs no keyboard hook, so it
works without elevated privileges and without a third-party dependency.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

VK_E = 0x45

HOTKEY_LABEL = "Ctrl+Shift+E"


class HotkeyListener(threading.Thread):
    HOTKEY_ID = 1

    def __init__(self, callback, logger: logging.Logger | None = None) -> None:
        super().__init__(name="quiter-hotkey", daemon=True)
        self.callback = callback
        self.log = logger or logging.getLogger(__name__)
        self.registered = False

        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._thread_id = 0

    def wait_ready(self, timeout: float = 2.0) -> bool:
        self._ready.wait(timeout)
        return self.registered

    def run(self) -> None:
        if sys.platform != "win32":
            self.log.debug("Global hotkeys are Windows-only; skipping")
            self._ready.set()
            return

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except OSError as exc:
            self.log.warning("Could not load Win32 libraries: %s", exc)
            self._ready.set()
            return

        self._thread_id = kernel32.GetCurrentThreadId()

        if not user32.RegisterHotKey(
            None,
            self.HOTKEY_ID,
            MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
            VK_E,
        ):
            error = ctypes.get_last_error()
            self.log.warning(
                "%s is already in use by another app (%s); hotkey disabled",
                HOTKEY_LABEL,
                ctypes.FormatError(error).strip(),
            )
            self._ready.set()
            return

        self.registered = True
        self._ready.set()
        self.log.info("Registered global hotkey %s", HOTKEY_LABEL)

        message = wintypes.MSG()
        try:
            while not self._stopped.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result in (0, -1):  # WM_QUIT or error
                    break
                if message.message == WM_HOTKEY and message.wParam == self.HOTKEY_ID:
                    self._fire()
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self.log.info("Hotkey listener stopped")

    def stop(self) -> None:
        self._stopped.set()
        self._ready.wait(2.0)
        if not self._thread_id:
            return
        try:
            user32 = ctypes.WinDLL("user32")
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        except OSError as exc:
            self.log.debug("Could not post WM_QUIT: %s", exc)

    def _fire(self) -> None:
        self.log.info("Hotkey %s pressed", HOTKEY_LABEL)
        try:
            self.callback()
        except Exception:
            self.log.exception("Hotkey callback failed")
