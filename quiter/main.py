"""Application entry point."""

from __future__ import annotations

import argparse
import ctypes
import logging

from .config import Config
from .hotkey import HotkeyListener
from .logsetup import setup_logging
from .pregame import Pregame
from .riot_local import RiotLocal
from .tray import TrayApp
from .worker import Worker

MUTEX_NAME = "Local\\valorant-quiter-single-instance"
_MUTEX_HANDLE = None


def _already_running() -> bool:
    """Windows named mutex so a second launch doesn't start a second poller."""
    global _MUTEX_HANDLE
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:  # not Windows
        return False

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return False
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return True
    _MUTEX_HANDLE = handle
    return False


def _notify_already_running(log: logging.Logger) -> None:
    log.info("Another instance is already running")
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "VALORANT Quiter is already running.\nCheck the system tray.",
            "VALORANT Quiter",
            0x40,  # MB_ICONINFORMATION
        )
    except AttributeError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="valorant-quiter",
        description="Quit the VALORANT pre-game (agent select) lobby from the tray.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="log to the console as well as to the log file",
    )
    args = parser.parse_args(argv)

    log = setup_logging(args.debug)

    if _already_running():
        _notify_already_running(log)
        return 0

    config = Config.load()
    local = RiotLocal()
    pregame = Pregame(local)
    worker = Worker(config, pregame, logger=logging.getLogger("quiter.worker"))
    tray = TrayApp(worker, logger=logging.getLogger("quiter.tray"))
    hotkey = HotkeyListener(worker.dodge_now, logger=logging.getLogger("quiter.hotkey"))

    log.info("Starting; auto-dodge is disarmed until you enable it")
    hotkey.start()
    try:
        tray.run()
    except KeyboardInterrupt:
        log.info("Interrupted")
    finally:
        worker.stop()
        hotkey.stop()
        log.info("Stopped")
    return 0
