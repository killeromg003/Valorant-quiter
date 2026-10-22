"""Talk to the Riot Client's local API (lockfile auth, no credentials needed)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import requests
import urllib3

from . import valorant_log
from .config import LOCALAPPDATA

log = logging.getLogger(__name__)

# The local API uses a self-signed certificate; the lockfile already proves we
# are the same user, so verification is pointless noise here.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOCKFILE = LOCALAPPDATA / "Riot Games" / "Riot Client" / "Config" / "lockfile"


class RiotNotRunning(RuntimeError):
    """The Riot Client lockfile is missing or unreadable."""


class RiotAuthError(RuntimeError):
    """The local Riot API rejected our lockfile credentials."""


@dataclass(frozen=True)
class Lockfile:
    port: int
    password: str
    protocol: str


@dataclass(frozen=True)
class Tokens:
    access_token: str
    entitlements: str
    puuid: str
    fetched_at: float


def read_lockfile() -> Lockfile:
    try:
        raw = LOCKFILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RiotNotRunning("Riot Client is not running") from exc
    except OSError as exc:
        raise RiotNotRunning(f"Could not read the Riot Client lockfile: {exc}") from exc

    # name:pid:port:password:protocol
    parts = raw.split(":")
    if len(parts) < 5:
        raise RiotNotRunning("Riot Client lockfile is malformed")

    try:
        port = int(parts[2])
    except ValueError as exc:
        raise RiotNotRunning("Riot Client lockfile has an invalid port") from exc

    return Lockfile(port=port, password=parts[3], protocol=parts[4])


class RiotLocal:
    """Cached access to the handful of local endpoints we need."""

    TOKEN_TTL = 25 * 60  # tokens live for an hour; refresh well before that

    def __init__(self, timeout: float = 4.0) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.verify = False
        self._tokens: Tokens | None = None
        self._version: str | None = None
        self.patchline: str | None = None

    def _get(self, lock: Lockfile, path: str) -> requests.Response:
        return self._session.get(
            f"https://127.0.0.1:{lock.port}{path}",
            auth=("riot", lock.password),
            timeout=self.timeout,
        )

    def tokens(self, force: bool = False) -> Tokens:
        if (
            self._tokens is not None
            and not force
            and time.monotonic() - self._tokens.fetched_at < self.TOKEN_TTL
        ):
            return self._tokens

        lock = read_lockfile()
        try:
            response = self._get(lock, "/entitlements/v1/token")
        except requests.RequestException as exc:
            raise RiotNotRunning(f"Riot Client is not reachable: {exc}") from exc

        if response.status_code == 401:
            raise RiotAuthError("Riot Client rejected the lockfile credentials")
        if response.status_code != 200:
            raise RiotAuthError(
                f"Entitlements request failed ({response.status_code})"
            )

        try:
            data = response.json()
            tokens = Tokens(
                access_token=data["accessToken"],
                entitlements=data["token"],
                puuid=data["subject"],
                fetched_at=time.monotonic(),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise RiotAuthError("Unexpected entitlements response") from exc

        self._tokens = tokens
        return tokens

    def client_version(self) -> str | None:
        """Version used in X-Riot-ClientVersion, e.g. release-10.10-shipping-..."""
        if self._version:
            return self._version

        sessions: dict = {}
        try:
            lock = read_lockfile()
            response = self._get(lock, "/product-session/v1/external-sessions")
            if response.status_code == 200:
                parsed = response.json()
                if isinstance(parsed, dict):
                    sessions = parsed
        except (RiotNotRunning, requests.RequestException, ValueError) as exc:
            log.debug("external-sessions unavailable: %s", exc)

        for session in sessions.values():
            if not isinstance(session, dict):
                continue
            if session.get("productId") != "valorant":
                continue
            self.patchline = session.get("patchlineId") or None
            if session.get("version"):
                self._version = str(session["version"])
                return self._version

        fallback = valorant_log.client_version()
        if fallback:
            self._version = fallback
        return fallback

    def region(self) -> str | None:
        try:
            response = self._get(read_lockfile(), "/riotclient/region-locale")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("region"):
                    return str(data["region"]).lower()
        except (RiotNotRunning, requests.RequestException, ValueError) as exc:
            log.debug("region-locale unavailable: %s", exc)
        return None
