"""Background polling loop: find a pre-game lobby, optionally quit it."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from .config import Config
from .pregame import GameNotRunning, Pregame, PregameError
from .riot_local import RiotAuthError, RiotNotRunning


@dataclass
class State:
    armed: bool = False
    in_pregame: bool = False
    status: str = "Starting..."
    error: bool = False
    dodges_today: int = 0


class Worker(threading.Thread):
    """Polls the pre-game player endpoint and quits on request.

    "Armed" (auto-dodge) is thread state only - it always starts False and is
    never persisted. The manual "Dodge now" action works regardless of arming.
    """

    def __init__(self, config: Config, pregame: Pregame, logger: logging.Logger | None = None) -> None:
        super().__init__(name="quiter-worker", daemon=True)
        self.config = config
        self.pregame = pregame
        self.log = logger or logging.getLogger(__name__)
        self.state = State(dodges_today=config.dodge_count)
        self.on_state = None  # type: ignore[assignment]

        self._lock = threading.Lock()
        self._armed = False
        self._manual = False
        self._stop = threading.Event()
        self._wake = threading.Event()

        self._last_match: str | None = None
        self._cooldown_until = 0.0
        self._snapshot: tuple | None = None

    # -- commands (safe to call from the tray thread) ---------------------

    def arm(self, value: bool | None = None) -> None:
        with self._lock:
            self._armed = (not self._armed) if value is None else bool(value)
            self.state.armed = self._armed
        self._publish()
        self._wake.set()

    def dodge_now(self) -> None:
        with self._lock:
            self._manual = True
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    # -- loop -------------------------------------------------------------

    def run(self) -> None:
        self.log.info("Worker started (auto-dodge off)")
        while not self._stop.is_set():
            with self._lock:
                armed = self._armed
                manual = self._manual
                self._manual = False

            delay = self.config.poll_interval
            try:
                match_id = self.pregame.find_match()
                if match_id is None:
                    self._last_match = None
                    if manual:
                        self._set_status("Not in agent select", error=False, in_pregame=False)
                    else:
                        self._set_status(
                            "Armed - waiting for agent select"
                            if armed
                            else "Idle - waiting for agent select",
                            error=False,
                            in_pregame=False,
                        )
                else:
                    self._handle_match(match_id, armed, manual)
            except RiotNotRunning as exc:
                self._set_status("Riot Client is not running", error=False, in_pregame=False)
                self.log.debug("%s", exc)
                delay = 5.0
            except GameNotRunning as exc:
                self._set_status("VALORANT is not running", error=False, in_pregame=False)
                self.log.debug("%s", exc)
                delay = 5.0
            except (RiotAuthError, PregameError) as exc:
                self._set_status(str(exc), error=True, in_pregame=False)
                self.log.warning("%s", exc)
                delay = 5.0
            except Exception as exc:  # keep the tray alive no matter what
                self._set_status(f"Unexpected error: {exc}", error=True, in_pregame=False)
                self.log.exception("Unexpected error in worker")
                delay = 5.0

            self._sleep(delay)

        self.log.info("Worker stopped")

    def _handle_match(self, match_id: str, armed: bool, manual: bool) -> None:
        now = time.monotonic()
        auto = (
            armed
            and match_id != self._last_match
            and now >= self._cooldown_until
        )

        if not (manual or auto):
            self._set_status(
                "In agent select - on cooldown"
                if armed
                else "In agent select - press Dodge now",
                error=False,
                in_pregame=True,
            )
            return

        if auto and not manual and self.config.dodge_delay > 0:
            self._set_status(
                f"In agent select - dodging in {self.config.dodge_delay:g}s",
                error=False,
                in_pregame=True,
            )
            self._sleep(self.config.dodge_delay)
            if self._stop.is_set():
                return
            with self._lock:
                still_armed = self._armed
            if not still_armed and not manual:
                self._set_status("Dodge cancelled - auto-dodge disarmed", error=False, in_pregame=True)
                return

        self._set_status("Dodging...", error=False, in_pregame=True)
        try:
            self.pregame.quit_match(match_id)
        except PregameError:
            self._last_match = match_id  # don't hammer the same lobby
            raise

        self._last_match = match_id
        self._cooldown_until = time.monotonic() + self.config.dodge_cooldown
        count = self.config.register_dodge()
        self.state.dodges_today = count
        self._set_status(f"Dodged - {count} today", error=False, in_pregame=False)
        self.log.info("Quit pre-game match %s (%d dodge(s) today)", match_id, count)
        if count >= self.config.warn_at:
            self.log.warning(
                "That is %d dodge(s) today - queue lockouts get longer each time", count
            )

    # -- helpers ----------------------------------------------------------

    def _set_status(self, text: str, *, error: bool, in_pregame: bool) -> None:
        if (
            text != self.state.status
            or error != self.state.error
            or in_pregame != self.state.in_pregame
        ):
            self.state.status = text
            self.state.error = error
            self.state.in_pregame = in_pregame
            self.log.debug("Status: %s", text)
            self._publish()

    def _publish(self) -> None:
        snapshot = (
            self.state.armed,
            self.state.in_pregame,
            self.state.status,
            self.state.error,
            self.state.dodges_today,
        )
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot
        if self.on_state is not None:
            try:
                self.on_state(self.state)
            except Exception:
                self.log.exception("State callback failed")

    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        self._wake.wait(seconds)
        self._wake.clear()
