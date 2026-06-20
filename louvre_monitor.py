"""Louvre free-ticket availability watcher (sibling routine to the plate watcher).

Polls ONE availability endpoint (captured from ticket.louvre.fr DevTools, set in
louvre_config.json or the LOUVRE_CHECK_URL secret) and emails when a slot opens
for a target date. It only NOTIFIES -- you book by hand on ticket.louvre.fr.

Recipients: the two Stephan addresses only (never Emil).

Reality check: ticket.louvre.fr sits behind anti-bot protection (DataDome). GitHub
Actions runs from datacenter IPs that such protection commonly blocks, so this
routine may report 'blocked' rather than real availability. It does NO evasion: on
a block it backs off and emails once. The plate watcher works in CI because its
backend is an open JSON API; the Louvre is not the same kind of target.

Shared with the plate watcher: notify.py (Gmail secrets GMAIL_USER / GMAIL_APP_PASSWORD).
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import sys

import requests

import notify

for _stream in (sys.stdout, sys.stderr):       # robust non-ASCII on Windows / CI
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CONFIG_FILE = pathlib.Path(os.environ.get("LOUVRE_CONFIG", "louvre_config.json"))
STATE_FILE = pathlib.Path(os.environ.get("LOUVRE_STATE_FILE", "louvre_state.json"))
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

# Stephan only -- Emil is intentionally excluded from this routine.
RECIPIENTS = ["stephan.kohlhaas@tum.de", "stkotum@gmail.com"]
BOOK_URL = "https://ticket.louvre.fr/"
BLOCK_NOTIFY_COOLDOWN = 21600  # 6 h between "I'm being blocked" emails

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BLOCK_MARKERS = ("datadome", "captcha", "are you a human", "access denied",
                 "request blocked", "just a moment", "unusual traffic",
                 "/cdn-cgi/challenge", "px-captcha")


class Blocked(Exception):
    """Raised when the request is challenged/blocked rather than answered."""


# --------------------------------------------------------------------------- #
# Config / state
# --------------------------------------------------------------------------- #

def load_config():
    if not CONFIG_FILE.exists():
        sys.exit(f"Config not found: {CONFIG_FILE} (see LOUVRE.md)")
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    # A session-bound URL is better kept in a secret than committed.
    env_url = os.environ.get("LOUVRE_CHECK_URL", "").strip()
    if env_url:
        cfg["check_url"] = env_url
    return cfg


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"initialized": False, "dates": {}, "last_run": None, "runs": 0,
            "blocked_notified": 0}


def save_state(state):
    state["last_run"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state["runs"] = state.get("runs", 0) + 1
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #

def is_configured(cfg):
    url = cfg.get("check_url", "")
    return bool(url) and "PASTE" not in url


def fetch(cfg):
    url = cfg["check_url"]
    headers = {"User-Agent": DEFAULT_UA,
               "Accept": "application/json, text/plain, */*",
               "Accept-Language": "en-GB,en;q=0.9,fr;q=0.8"}
    headers.update(cfg.get("headers", {}))
    timeout = cfg.get("request_timeout", 20)
    method = cfg.get("method", "GET").upper()

    if method == "POST":
        body = cfg.get("post_body")
        if isinstance(body, (dict, list)):
            r = requests.post(url, json=body, headers=headers, timeout=timeout)
        else:
            r = requests.post(url, data=body, headers=headers, timeout=timeout)
    else:
        r = requests.get(url, headers=headers, timeout=timeout)

    if r.status_code in (401, 403, 429, 503):
        raise Blocked(f"HTTP {r.status_code}")
    if any(m in r.text[:4000].lower() for m in BLOCK_MARKERS):
        raise Blocked("challenge/CAPTCHA page")
    if r.status_code != 200:
        raise RuntimeError(f"unexpected HTTP {r.status_code}")
    return r


# --------------------------------------------------------------------------- #
# Availability detection (ported from the standalone watcher)
# --------------------------------------------------------------------------- #

def date_variants(iso_date):
    y, m, d = iso_date.split("-")
    return {iso_date, f"{d}/{m}/{y}", f"{m}/{d}/{y}", f"{d}-{m}-{y}", f"{y}{m}{d}"}


_AVAIL_KEY_RE = re.compile(r"avail|remain|free|place|quota|stock|capacity|"
                           r"bookable|sellable|open|count|slot", re.I)
_POSITIVE_STR = re.compile(r"avail|open|bookable|libre|disponible", re.I)


def _object_signals_available(obj):
    for k, v in obj.items():
        if not _AVAIL_KEY_RE.search(str(k)):
            continue
        if isinstance(v, bool):
            if v:
                return True
        elif isinstance(v, (int, float)):
            if v > 0:
                return True
        elif isinstance(v, str):
            if _POSITIVE_STR.search(v) or (v.strip().isdigit() and int(v) > 0):
                return True
        elif isinstance(v, (list, tuple)):
            if len(v) > 0:
                return True
    return False


def _json_date_available(node, variants, notify_on_present):
    if isinstance(node, dict):
        for k, v in node.items():
            if any(var in str(k) for var in variants):
                if isinstance(v, (list, tuple)):
                    if len(v) > 0:
                        return True
                elif isinstance(v, dict):
                    if _object_signals_available(v) or notify_on_present:
                        return True
                elif notify_on_present:
                    return True
        has_date = any(any(var in str(v) for var in variants)
                       for v in node.values() if isinstance(v, (str, int)))
        if has_date and (_object_signals_available(node) or notify_on_present):
            return True
        return any(_json_date_available(v, variants, notify_on_present)
                   for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_json_date_available(v, variants, notify_on_present) for v in node)
    if isinstance(node, (str, int)):
        # A bare date scalar (e.g. inside an "availableDates" list) counts as
        # available only in present-mode; quota-mode needs an explicit signal.
        return bool(notify_on_present and any(var in str(node) for var in variants))
    return False


def detect_for_date(resp, iso_date, cfg):
    """Return True/False/None (None = couldn't decide)."""
    detect = cfg.get("detect", {})
    mode = detect.get("mode", "auto")
    text = resp.text
    variants = date_variants(iso_date)

    avail_markers = detect.get("available_contains", [])
    unavail_markers = detect.get("unavailable_contains", [])
    if avail_markers:
        return any(m in text for m in avail_markers)
    if unavail_markers:
        return not any(m in text for m in unavail_markers)

    ctype = resp.headers.get("Content-Type", "")
    if mode in ("auto", "json_dates") and ("json" in ctype.lower() or mode == "json_dates"):
        try:
            data = resp.json()
        except ValueError:
            data = None
        if data is not None:
            return _json_date_available(data, variants,
                                        detect.get("notify_on_date_present", True))

    if mode in ("auto", "text"):
        return any(var in text for var in variants)
    return None


# --------------------------------------------------------------------------- #
# Email bodies
# --------------------------------------------------------------------------- #

def _email_open(dates):
    lines = ["A Louvre slot appears AVAILABLE for:", ""]
    lines += [f"  - {d}" for d in dates]
    lines += ["",
              "Book it yourself now (free under-26 = EEA residency, bring ID):",
              BOOK_URL, "", "-- louvre watcher (sibling of the plate watcher)"]
    return "\n".join(lines)


def _email_report(results):
    lines = ["Louvre watch - status report", ""]
    for d, ok in results.items():
        lines.append(f"  {d}: {'AVAILABLE' if ok else 'no availability'}")
    lines += ["", f"Booking: {BOOK_URL}", "", "-- louvre watcher"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description="Louvre availability watcher routine.")
    ap.add_argument("--report", action="store_true",
                    help="email current status for all target dates + re-baseline")
    ap.add_argument("--dry-run", action="store_true", help="never email; just print")
    ap.add_argument("--test-email", action="store_true",
                    help="send a credentials test to Stephan and exit")
    args = ap.parse_args()

    if args.test_email:
        notify.send_simple("Louvre watch - test email",
                           "Louvre routine email credentials work.\n\n-- louvre watcher",
                           RECIPIENTS)
        return

    dry = DRY_RUN or args.dry_run
    cfg = load_config()
    dates = cfg.get("target_dates", [])
    state = load_state()
    print(f"=== Louvre watch === {datetime.datetime.now().isoformat(timespec='seconds')} "
          f"(dry_run={dry}) dates={dates}")

    if not is_configured(cfg):
        # Benign no-op (exit 0) so scheduled runs stay green until you capture the
        # availability request -- see LOUVRE.md. No red failures, no failure emails.
        print("  endpoint not configured yet (set check_url in louvre_config.json "
              "or the LOUVRE_CHECK_URL secret). Nothing to do.")
        return

    try:
        resp = fetch(cfg)
    except Blocked as e:
        print(f"  ! blocked: {e} -- backing off, state untouched.")
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if not dry and (now - state.get("blocked_notified", 0)) > BLOCK_NOTIFY_COOLDOWN:
            notify.send_simple(
                "Louvre watch - being blocked",
                "ticket.louvre.fr is returning a block/challenge page (likely "
                "DataDome blocking GitHub's datacenter IPs, or an expired "
                "session URL). Backing off. You may need to re-capture the "
                "request from DevTools into the LOUVRE_CHECK_URL secret.\n\n"
                "-- louvre watcher", RECIPIENTS)
            state["blocked_notified"] = now
            save_state(state)
        sys.exit(0)
    except Exception as e:  # noqa: BLE001
        print(f"  ! error: {e} -- state untouched.")
        sys.exit(0)

    results, newly_open = {}, []
    prev = state.get("dates", {})
    for d in dates:
        ok = detect_for_date(resp, d, cfg)
        if ok is None:
            print(f"  [{d}] undecided -- check detect/* in louvre_config.json")
            results[d] = False
            continue
        results[d] = ok
        print(f"  [{d}] {'AVAILABLE' if ok else 'no availability'}")
        if ok and not prev.get(d, False):
            newly_open.append(d)

    want_report = args.report or not state.get("initialized")
    if dry:
        print("(dry-run: no email, state NOT saved)")
        return

    if want_report:
        print(f"  full report -> {RECIPIENTS}")
        notify.send_simple(
            f"Louvre watch - status report ({sum(results.values())} available)",
            _email_report(results), RECIPIENTS)
    elif newly_open:
        print(f"  NEWLY AVAILABLE {newly_open} -> {RECIPIENTS}")
        notify.send_simple(f"ALERT: Louvre slot open ({', '.join(newly_open)})",
                           _email_open(newly_open), RECIPIENTS)
    else:
        print("  no change")

    state["initialized"] = True
    state["dates"] = results
    save_state(state)


if __name__ == "__main__":
    main()
