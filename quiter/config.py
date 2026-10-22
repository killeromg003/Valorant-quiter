"""Persistent settings and the per-day dodge counter."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
APP_DIR = LOCALAPPDATA / "valorant-quiter"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "quiter.log"


def _clamp(value: object, low: float, high: float, default: float) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return min(max(number, low), high)


@dataclass
class Config:
    """User settings.

    Deliberately has no ``auto_dodge`` field: the tray toggle always starts
    disarmed and is never written to disk.
    """

    poll_interval: float = 1.0
    dodge_delay: float = 0.0
    dodge_cooldown: float = 10.0
    warn_at: int = 3
    dodge_count: int = 0
    dodge_date: str = ""

    @classmethod
    def load(cls) -> "Config":
        raw: dict = {}
        try:
            parsed = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                raw = parsed
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("Could not read %s: %s", CONFIG_PATH, exc)

        known = {field.name for field in dataclasses.fields(cls)}
        cfg = cls(**{key: value for key, value in raw.items() if key in known})
        cfg._normalise()
        return cfg

    def save(self) -> None:
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(dataclasses.asdict(self), indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            log.warning("Could not write %s: %s", CONFIG_PATH, exc)

    def register_dodge(self) -> int:
        """Count one dodge for today and return the new total."""
        self._roll_over()
        self.dodge_count += 1
        self.save()
        return self.dodge_count

    def _normalise(self) -> None:
        self.poll_interval = _clamp(self.poll_interval, 0.25, 10.0, 1.0)
        self.dodge_delay = _clamp(self.dodge_delay, 0.0, 60.0, 0.0)
        self.dodge_cooldown = _clamp(self.dodge_cooldown, 1.0, 300.0, 10.0)
        self.warn_at = int(_clamp(self.warn_at, 1, 50, 3))
        self.dodge_count = int(_clamp(self.dodge_count, 0, 10_000, 0))
        self._roll_over()

    def _roll_over(self) -> None:
        today = date.today().isoformat()
        if self.dodge_date != today:
            self.dodge_date = today
            self.dodge_count = 0
