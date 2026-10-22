"""Pre-game (agent select) lookups and the quit call."""

from __future__ import annotations

import logging

import requests

from . import valorant_log
from .riot_local import RiotLocal, Tokens

log = logging.getLogger(__name__)

# Base64 of the platform JSON from the API docs; still accepted by Riot.
CLIENT_PLATFORM = (
    "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lv"
    "biI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9"
)

# /riotclient/region-locale reports both the documented regions (na, eu, ...)
# and sub-regions (tw2, sg2, ...). Map both to the region used in glz hosts.
GLZ_REGION = {
    "na": "na",
    "latam": "latam",
    "br": "br",
    "eu": "eu",
    "ap": "ap",
    "kr": "kr",
    "tw2": "ap",
    "sg2": "ap",
    "hk": "ap",
    "jp": "ap",
    "th": "ap",
    "my": "ap",
    "id": "ap",
    "ph": "ap",
    "vn": "ap",
    "oc": "ap",
}

SHARD_BY_GLZ_REGION = {
    "na": "na",
    "latam": "na",
    "br": "na",
    "eu": "eu",
    "ap": "ap",
    "kr": "kr",
}


class PregameError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class GameNotRunning(PregameError):
    """VALORANT isn't running, so we have no client version / match to act on."""


class Pregame:
    """Resolves the glz host lazily and keeps auth fresh across calls."""

    def __init__(self, local: RiotLocal, timeout: float = 6.0) -> None:
        self._local = local
        self._session = requests.Session()
        self._timeout = timeout
        self._tokens: Tokens | None = None
        self._version: str | None = None
        self._host: str | None = None

    def _auth(self, refresh: bool = False) -> tuple[Tokens, str]:
        self._tokens = self._local.tokens(force=refresh)
        if self._version is None:
            self._version = self._local.client_version()
        if not self._version:
            # The version only exists in external-sessions while the game runs.
            raise GameNotRunning("VALORANT is not running")
        return self._tokens, self._version

    def _resolve_host(self) -> str:
        target = valorant_log.glz_target()
        if target:
            region, shard = target
        else:
            sub_region = self._local.region()
            region = GLZ_REGION.get(sub_region or "")
            if not region:
                raise PregameError(
                    f"Could not determine region (region-locale said {sub_region!r})"
                )
            shard = "pbe" if self._local.patchline == "pbe" else SHARD_BY_GLZ_REGION[region]

        host = f"https://glz-{region}-1.{shard}.a.pvp.net"
        log.debug("Using glz host %s", host)
        return host

    def _request(self, method: str, path: str, expected: tuple[int, ...]) -> requests.Response:
        for attempt in (0, 1):
            tokens, version = self._auth(refresh=attempt == 1)
            if self._host is None:
                self._host = self._resolve_host()

            headers = {
                "Authorization": f"Bearer {tokens.access_token}",
                "X-Riot-Entitlements-JWT": tokens.entitlements,
                "X-Riot-ClientVersion": version,
                "X-Riot-ClientPlatform": CLIENT_PLATFORM,
            }

            try:
                response = self._session.request(
                    method,
                    self._host + path,
                    headers=headers,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                # The host may have changed (other region / PBE); re-resolve next time.
                self._host = None
                raise PregameError(f"Could not reach Riot: {exc}") from exc

            if attempt == 0 and response.status_code in (401, 403):
                log.debug("%s %s returned %s, refreshing tokens", method, path, response.status_code)
                continue

            if response.status_code in expected or response.status_code == 404:
                return response

            raise PregameError(
                f"{method} {path} failed ({response.status_code})",
                response.status_code,
                response.text[:300],
            )

        raise PregameError("Riot kept rejecting our tokens after a refresh", 401)

    def find_match(self) -> str | None:
        """Return the current pre-game match ID, or None when not in agent select."""
        tokens, _ = self._auth()
        response = self._request("GET", f"/pregame/v1/players/{tokens.puuid}", (200,))
        if response.status_code == 404:
            return None
        try:
            data = response.json()
        except ValueError as exc:
            raise PregameError("Pre-game player response was not JSON") from exc
        match_id = data.get("MatchID") if isinstance(data, dict) else None
        return str(match_id) if match_id else None

    def quit_match(self, match_id: str) -> None:
        response = self._request("POST", f"/pregame/v1/matches/{match_id}/quit", (200, 204))
        if response.status_code == 404:
            raise PregameError("Match no longer exists", 404, response.text[:300])
