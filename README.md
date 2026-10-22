# VALORANT Quiter

A tiny Windows tray app that quits the VALORANT pre-game lobby (agent select) via
Riot's own client API. No passwords, no client injection - it reuses the tokens the
Riot Client already keeps in its lockfile.

## Install

Requires Windows and Python 3.10+.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\pythonw run.pyw
```

`pythonw` is the windowless interpreter, so there is no console. Double-clicking
`run.pyw` works too if your `.venv` Python is the one associated with `.pyw` files
(create a shortcut to `.venv\Scripts\pythonw.exe run.pyw` if unsure).

For troubleshooting, run with a console:

```powershell
.venv\Scripts\python -m quiter --debug
```

The Riot Client (and VALORANT, for agent select to exist) must be running.

## Tray menu

| Item | What it does |
| --- | --- |
| **Dodge now** | Quits the current agent-select lobby immediately. Also on **Ctrl+Shift+E**, system-wide. |
| **Auto-dodge** | When checked, dodges automatically as soon as a pre-game lobby appears. Always starts **off**; it is never remembered between launches. This is the default item, so a plain left click on the icon toggles it. |
| **Status** | What the poller is currently doing. |
| **Dodges today** | Per-day counter, reset at midnight and stored in the config file. |
| **Open log** | Opens `%LOCALAPPDATA%\valorant-quiter\quiter.log`. |
| **Quit** | Stops the poller and exits. |

Right-click the icon for the menu; left-click toggles auto-dodge. (Windows treats
the default item as the left-click action, and a single stray click should not be
able to quit a lobby.)

**Ctrl+Shift+E** dodges from anywhere, including while VALORANT is focused. It uses
Win32 `RegisterHotKey`, so it works without running as administrator and without
installing a keyboard-hook library. If another app already owns the combination,
the hotkey is skipped and a warning is written to the log; everything else keeps
working. Note that the registration is system-wide and takes precedence over the
same combo elsewhere (VS Code uses Ctrl+Shift+E for its Explorer view).

Icon colours: grey = idle, green = auto-dodge armed, amber = in agent select,
red = error (the tooltip has the message).

## How it works

1. Reads `%LocalAppData%\Riot Games\Riot Client\Config\lockfile` for the local API
   port and password, then fetches the access token, entitlement JWT and PUUID from
   `https://127.0.0.1:{port}/entitlements/v1/token`.
2. Gets the client version from `/product-session/v1/external-sessions`, falling
   back to `CI server version:` in `ShooterGame.log`.
3. Resolves the glz host from a `https://glz-{region}-1.{shard}.a.pvp.net` URL in
   `ShooterGame.log`, falling back to `/riotclient/region-locale` plus the shard table.
4. Polls `GET /pregame/v1/players/{puuid}` about once a second. A 404 simply means
   "not in agent select".

   We only call Riot when the endpoint returns a match ID:

   ```
   POST /pregame/v1/matches/{matchId}/quit
   ```

   The same match is never quit twice, and after a successful dodge there is a short
   cooldown to let the lobby tear down.

## Configuration

`%LOCALAPPDATA%\valorant-quiter\config.json`, created on first dodge:

```json
{
  "poll_interval": 1.0,
  "dodge_delay": 0.0,
  "dodge_cooldown": 10.0,
  "warn_at": 3,
  "dodge_count": 1,
  "dodge_date": "2026-10-22"
}
```

| Key | Meaning |
| --- | --- |
| `poll_interval` | Seconds between pre-game checks (0.25-10). |
| `dodge_delay` | Optional delay before an *auto* dodge (0-60). Manual dodges ignore it. |
| `dodge_cooldown` | Seconds to wait after a dodge before auto-dodging again (1-300). |
| `warn_at` | Dodge count at which the log starts warning about penalties. |

Note there is no `auto_dodge` key: arming is per-session on purpose.

## Warnings

- **Dodging has penalties.** Each dodge in a short window lengthens your queue
  lockout, and repeated dodging can escalate to ranked restrictions. The per-day
  counter and the warning line in the log exist so this is visible rather than
  silent. You are responsible for how you use it.
- This is an unofficial tool built on undocumented Riot endpoints. It may stop
  working after a game update, and using it is at your own risk with respect to
  Riot's terms of service.
- It needs the Riot Client running locally; there is no remote/credential mode.

## Troubleshooting

- **"Riot Client is not running"** - start the Riot Client. The lockfile only
  exists while it is open.
- **"VALORANT is not running"** - only the Riot Client is up. The client version
  needed for the pre-game calls comes from the game's own session, so the poller
  idles until VALORANT starts (it checks every few seconds).
- **"Could not determine region"** - launch VALORANT once so `ShooterGame.log`
  contains a glz URL, or check that `/riotclient/region-locale` responds.
- **"Match no longer exists"** - the lobby ended before the quit landed; harmless.
- **403/401** - tokens were refreshed automatically once; if it persists, restart
  the Riot Client.
- **Nothing happens on Dodge now** - you are not in agent select; the status line
  says so.
- **Ctrl+Shift+E does nothing** - another application registered that combination
  first. The log (`quiter.log`) has a "already in use" warning. No other part of
  the app is affected.
