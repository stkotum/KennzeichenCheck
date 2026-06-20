# Wunschkennzeichen watcher (Freising + Esslingen/Nürtingen)

Watches license-plate availability across multiple districts and **emails on changes**,
with **per-recipient routing**:

| Group | Plates watched | Emailed to |
|-------|----------------|-----------|
| **FS** (Freising) | `FS-??-1` (any letters + №1), and single-digit `FS-SK/KH/ST/KO/RT/OO/ZZ/YY/XX-?` | stephan.kohlhaas@tum.de, stkotum@gmail.com |
| **ES/NT** (Esslingen, Nürtingen) | **number 1 only**: `ES-AZ/EH/HN-1` and `NT-AZ/EH/HN-1` | the two above **+ emil.hennrich@gmx.net** |

Emil only ever receives ES/NT alerts; the FS plates are never sent to him.
FS watches all single-digit numbers; ES/NT watch **number 1 only**. The **first run after (re)deploy emails a full
status report** (current availability) to each audience; **every later run emails only changes**,
subject prefixed `ALERT:`.

> **Sibling routine:** this repo also runs a **Louvre ticket watcher** (separate
> workflow + state, same email plumbing, Stephan-only). See **[LOUVRE.md](LOUVRE.md)**.

## How it works
- Calls the public availability endpoint (`backend.wunschkennzeichen-reservieren.jetzt/reservation-checks`)
  per district `officeId`. No auth, no browser, ASCII-only emails (so strict filters don't quarantine).
- **FS** is an i-Kfz office: one wildcard request enumerates availability per family.
- **ES/NT** are intelliform offices where wildcards are unreliable, so each pair is probed across
  digits 1–9 individually. A full run is ~60 light requests — fine hourly.
- It only **notifies**; you reserve on the district's official portal yourself (~2.60 €, 90 days).

## Office IDs
- FS Freising `5f17f89ddff4262e1b32f4ed` · ES Esslingen `5f17f89ddff4262e1b32f4da` · NT Nürtingen `5f17f89ddff4262e1b32f62a`

## Files
| File | Purpose |
|------|---------|
| `checker.py` | endpoint calls (`available_letters/numbers`, `check_plate`), office-aware |
| `monitor.py` | families, **audiences/recipient routing**, sweep, report/changes |
| `notify.py` | sends report / change / test emails (explicit recipient lists) |
| `state.json` | baseline of what's available (dedup + heartbeat) |
| `.github/workflows/check.yml` | hourly GitHub Actions run |
| `vai_search.py`, `bw_check.py`, `scout.py`, `verify_endpoint.py`, `test_logic.py` | one-off lookups / dev tools |

## Recipients / adding watches
Recipients and the watch list live at the top of `monitor.py` (`OWNER`, `EMIL`, `AUDIENCES`,
`FAMILIES`). To add a pair, append a `_fam(...)` entry (mode `numbers` for i-Kfz offices like FS,
mode `digits` for intelliform offices like ES/NT). To change who gets what, edit `AUDIENCES`.

## Run / test
```powershell
.\.venv\Scripts\python.exe monitor.py --report --dry-run   # all districts, no email, no state change
.\.venv\Scripts\python.exe monitor.py --report             # full report + baseline
.\.venv\Scripts\python.exe monitor.py                       # normal: email only changes
.\.venv\Scripts\python.exe monitor.py --test-email          # credentials test to owner
.\.venv\Scripts\python.exe test_logic.py                    # offline routing/format tests
```
Secrets (GitHub Actions / `.env`): `GMAIL_USER`, `GMAIL_APP_PASSWORD`. Schedule/cron in
`.github/workflows/check.yml`. On-demand report: Actions tab → Run workflow → tick "report".
