"""Read the few things we need out of VALORANT's ShooterGame.log."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .config import LOCALAPPDATA

log = logging.getLogger(__name__)

SHOOTER_LOG = LOCALAPPDATA / "VALORANT" / "Saved" / "Logs" / "ShooterGame.log"

_GLZ = re.compile(r"https://glz-([a-z0-9]+)-1\.([a-z0-9]+)\.a\.pvp\.net")
_VERSION = re.compile(r"CI server version:\s*(\S+)")

# The relevant lines are near the end; don't parse a 100 MB log every second.
_TAIL_BYTES = 2 * 1024 * 1024


def _tail(path: Path | None = None) -> str:
    path = path or SHOOTER_LOG
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    try:
        with open(path, "rb") as handle:
            if size > _TAIL_BYTES:
                handle.seek(size - _TAIL_BYTES)
            return handle.read().decode("utf-8", "ignore")
    except OSError as exc:
        log.debug("Could not read %s: %s", path, exc)
        return ""


def glz_target() -> tuple[str, str] | None:
    """Return ``(region, shard)`` from a glz URL the game has used, if any."""
    matches = _GLZ.findall(_tail())
    return matches[-1] if matches else None


def client_version() -> str | None:
    """Fallback source for the client version header."""
    matches = _VERSION.findall(_tail())
    return matches[-1] if matches else None
