# FS Wunschkennzeichen watcher (Freising)

Watches **six plate queries** and emails **stephan.kohlhaas@tum.de** when anything changes:

| Query | Meaning |
|-------|---------|
| `FS-??-1` | any two letters + the number **1** (the rare "dream" plate) |
| `FS-SK-?` | letters **SK** (your initials) + a **single-digit** number (1–9) |
| `FS-KH-?` | letters **KH** + a **single-digit** number (1–9) |
| `FS-ST-?` | letters **ST** + a **single-digit** number (1–9) |
| `FS-KO-?` | letters **KO** + a **single-digit** number (1–9) |
| `FS-RT-?` | letters **RT** + a **single-digit** number (1–9) |

Only single-digit numbers are considered (never multi-digit). The **first run emails a full
status report** of all six; **every later run emails only what changed** (newly available / no
longer available). Single-digit plates are coveted and rarely free, so mostly it just waits.

### Current status (live, at build time)
- `FS-??-1`: **none** available.
- `FS-SK-?`, `FS-KH-?`, `FS-ST-?`: **none** — all of 1–9 taken.
- `FS-KO-?`: available **4, 5, 6, 8, 9**; still taken (watching) **1, 2, 3, 7**.
- `FS-RT-?`: **none** single-digit available; all of 1–9 taken.

## How it works (and what it is not)

- **It does not "hack a database."** It calls the *same public availability check* you'd use by
  hand. The source is the official Freising checker exposed via `wunschkennzeichen-reservieren.jetzt`,
  which queries the authority's i-Kfz system (Freising `officeId` `5f17f89ddff4262e1b32f4ed`,
  i-Kfz key `09178000`). The endpoint returns a clean `isAvailable` boolean and, when you leave the
  letters **or** the number blank, the full list of free combinations for the other field.
- **Each run is just 6 HTTP requests** (one per query) — extremely light and polite. Hourly is no
  problem.
- **It only notifies; it does not reserve.** When you get an email, reserve it yourself on the
  official portal: <https://www.buergerserviceportal.de/bayern/lkrfreising/igvwkz>
  (~2.60 €, holds the plate 90 days). Act fast — short plates go quickly.

## Files

| File | Purpose |
|------|---------|
| `checker.py` | the 3 endpoint calls: `available_letters(num)`, `available_numbers(letters)`, `check_plate()` |
| `notify.py` | sends the report / change / test emails via Gmail SMTP |
| `monitor.py` | runs the 3 queries, diffs vs `state.json`, emails report or changes |
| `state.json` | baseline of what's currently available (prevents repeat emails; also a heartbeat) |
| `.github/workflows/check.yml` | runs `monitor.py` hourly on GitHub Actions |
| `run_local.ps1` | PC fallback via Windows Task Scheduler |
| `plates.py` | reference: rules + generator of all valid `FS-??-1` letter pairs |
| `scout.py`, `verify_endpoint.py`, `test_logic.py` | dev/diagnostic tools + offline tests |

## Setup (GitHub Actions — your chosen 24/7 option)

1. **Make a Gmail App password** for the sender `stkotum@gmail.com`:
   enable 2-Step Verification, then create one at <https://myaccount.google.com/apppasswords>
   (16 characters).

2. **Push this folder to a private GitHub repo:**
   ```bash
   git init && git add . && git commit -m "FS plate watcher"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

3. **Add repository secrets** (Settings → Secrets and variables → Actions → *New repository secret*):
   - `GMAIL_USER` = `stkotum@gmail.com`
   - `GMAIL_APP_PASSWORD` = the 16-char app password
   - `ALERT_TO` = `stephan.kohlhaas@tum.de` *(optional; already the default)*

4. **Get the initial report now:** Actions tab → **FS-1 plate watcher** → **Run workflow**.
   The first run emails the full status report and stores the baseline. Check the log: it should
   print 3 lines (one per query). **If you see `blocked` / HTTP 403 / 429**, GitHub's US IP is being
   filtered — use the PC fallback below (your German IP works cleanly; verified).

5. Done. It runs hourly and emails only changes. `state.json` is committed each run (heartbeat, so
   GitHub never auto-disables the schedule). Cron is UTC and can be delayed 5–15 min under load — fine here.

## PC fallback (German IP, if Actions ever gets blocked)

Everything is already installed locally:
```powershell
cp .env.example .env                                   # then put your app password in .env
.\.venv\Scripts\python.exe monitor.py --test-email     # confirm email works
.\.venv\Scripts\python.exe monitor.py --report         # send the initial report now
schtasks /Create /SC HOURLY /TN "FS1PlateWatcher" /TR `
  "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PWD\run_local.ps1`""
```
Downside: only checks while the PC is on/awake.

## Local usage

```powershell
.\.venv\Scripts\python.exe monitor.py --report --dry-run   # show all 3 queries, no email, no state change
.\.venv\Scripts\python.exe monitor.py --report             # send full report + set baseline
.\.venv\Scripts\python.exe monitor.py                      # normal run: email only changes
.\.venv\Scripts\python.exe monitor.py --test-email         # send a test email
.\.venv\Scripts\python.exe test_logic.py                   # offline unit tests
```

## Changing what's watched

Edit the `FAMILIES` list at the top of `monitor.py`. Examples:
- watch only one exact plate: add `check_plate("SK", "1")` logic, or a `letters`/`number` pair.
- add another letter pair (e.g. `MH`): copy a `"numbers"` family with `"letters": "MH"`.
- allow multi-digit again: remove the `SINGLE_DIGITS` filter in `sweep()`.
To change frequency, edit the `cron` line in `.github/workflows/check.yml`
(`"7 */3 * * *"` = every 3 hours).
