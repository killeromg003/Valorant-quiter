"""The tray icon, its menu, and the state -> icon mapping."""

from __future__ import annotations

import logging
import os

import pystray

from . import icons
from .config import LOG_PATH
from .hotkey import HOTKEY_LABEL
from .worker import State, Worker

TOOLTIP_LIMIT = 120


class TrayApp:
    def __init__(self, worker: Worker, logger: logging.Logger | None = None) -> None:
        self.worker = worker
        self.log = logger or logging.getLogger(__name__)
        self.state: State = worker.state

        self.icon = pystray.Icon(
            "valorant-quiter",
            icon=icons.make_icon("off"),
            title="VALORANT Quiter",
            menu=self._build_menu(),
        )
        worker.on_state = self._on_state

    # -- menu -------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(f"Dodge now\t{HOTKEY_LABEL}", self._dodge),
            pystray.MenuItem(
                "Auto-dodge",
                self._toggle_arm,
                checked=lambda item: self.state.armed,
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: f"Status: {self.state.status}",
                action=None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda item: f"Dodges today: {self.state.dodges_today}",
                action=None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open log", self._open_log),
            pystray.MenuItem("Quit", self._quit),
        )

    def _dodge(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.log.info("Dodge requested from tray")
        self.worker.dodge_now()

    def _toggle_arm(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.worker.arm()
        self.log.info("Auto-dodge %s", "armed" if self.state.armed else "disarmed")

    def _open_log(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            os.startfile(LOG_PATH)  # type: ignore[attr-defined]
        except OSError as exc:
            self.log.warning("Could not open %s: %s", LOG_PATH, exc)

    def _quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.worker.stop()
        icon.stop()

    # -- state ------------------------------------------------------------

    def _icon_kind(self, state: State) -> str:
        if state.error:
            return "error"
        if state.in_pregame:
            return "pregame"
        if state.armed:
            return "armed"
        return "off"

    def _on_state(self, state: State) -> None:
        tooltip = f"VALORANT Quiter - {state.status}"
        self.icon.icon = icons.make_icon(self._icon_kind(state))
        self.icon.title = tooltip[:TOOLTIP_LIMIT]
        try:
            self.icon.update_menu()
        except Exception:  # menu may not be attached yet during startup
            self.log.debug("update_menu failed", exc_info=True)

    # -- lifecycle --------------------------------------------------------

    def run(self) -> None:
        self.worker.start()
        self.icon.run()
