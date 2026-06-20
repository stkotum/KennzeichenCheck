# Louvre ticket watcher (sibling routine)

A second routine in this repo, independent of the plate watcher. It polls one
availability endpoint on `ticket.louvre.fr` and **emails when a slot opens** for a
target date. It only **notifies** — you book by hand on https://ticket.louvre.fr/.

**Emails go to Stephan only** (`stephan.kohlhaas@tum.de`, `stkotum@gmail.com`) —
Emil is intentionally excluded from this routine.

> ⚠️ **This may not work from GitHub Actions.** `ticket.louvre.fr` sits behind
> anti-bot protection (DataDome). GitHub's runners use datacenter IPs that such
> protection commonly blocks, so the routine may just email "being blocked"
> instead of real availability. It does **no** evasion by design. The plate
> watcher works in CI because its backend is an open JSON API; the Louvre isn't.
> If CI gets blocked, run `louvre_monitor.py` from your own machine on a schedule
> instead (same code, residential IP).
>
> ⚠️ Free under-26 entry is **EEA-residency based**, not just "student" — ID is
> checked at the door. And next Friday is inside the 90-day window, so **try
> booking manually first**; you may not need this at all.

## Files (all prefixed `louvre_`, so the plate watcher is untouched)
| File | Purpose |
|------|---------|
| `louvre_monitor.py` | entry point: fetch, detect, email via shared `notify.py`, keep state |
| `louvre_config.json` | the availability request + target dates + detection rules |
| `louvre_state.json` | last-seen availability per date (dedup + heartbeat) |
| `.github/workflows/louvre.yml` | its own schedule (`:23,:53`), commits `louvre_state.json` |

It reuses the plate watcher's `notify.py` and the **same Gmail secrets**
(`GMAIL_USER`, `GMAIL_APP_PASSWORD`) — nothing new to configure for email.

## The one manual step: capture the availability request
The endpoint is session-specific, so you grab it from your browser once:
1. Open https://ticket.louvre.fr/ → start a free booking to the **calendar/slot** screen.
2. **F12 → Network → Fetch/XHR**, tick **Preserve log**, click around the calendar.
3. Find the request whose JSON response lists dates/slots (look for `availability`,
   `slots`, `quota`, or your date `2026-06-26`). Copy its **URL** (and payload if POST).
4. Put it in **`louvre_config.json`** (`check_url`, `method`, `post_body`, `headers`),
   **or** — better for a session-bound URL — store it in an Actions **secret** named
   `LOUVRE_CHECK_URL` (Settings → Secrets and variables → Actions). The secret
   overrides the file.

Tune `detect`:
- `mode`: `auto` (default), `text`, or `json_dates`.
- `notify_on_date_present`: many Secutix calendars return **only bookable dates**,
  so the date merely appearing = open (leave `true`). If the endpoint returns all
  dates with a quota field, set `false`.
- `available_contains` / `unavailable_contains`: exact-string overrides; if set,
  `available_contains` wins over everything (most reliable when you spot a marker).

## Run / test
```powershell
python louvre_monitor.py --test-email     # credentials test to Stephan
python louvre_monitor.py --dry-run        # fetch + detect, no email, no state write
python louvre_monitor.py --report         # email current status + baseline
python louvre_monitor.py                  # normal: email only newly-open dates
```
On-demand from CI: Actions tab → **Louvre ticket watcher** → Run workflow (tick
"report" for a full status email).

## Behaviour
- First run (or `--report`) emails a full status report; later runs email only a
  fresh **no→yes** transition per date (`ALERT:` subject), then state dedups so you
  aren't re-spammed.
- On a block/challenge it backs off and emails **once per 6 h**, leaving state
  otherwise untouched.
