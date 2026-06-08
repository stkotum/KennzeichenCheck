"""Watch three FS Wunschkennzeichen queries and email on changes.

Queries (all single-digit numbers only, per request):
  FS-??-1   any two letters + the number 1        (the rare "dream" plate)
  FS-KO-?   letters KO + a single-digit number 1..9
  FS-RT-?   letters RT + a single-digit number 1..9

Each query is a SINGLE backend request (letters- or number-wildcard enumeration),
so a full run is just 3 requests — very light, polite, and fast.

Behaviour:
  * First ever run (state not initialised) OR `--report`: emails a FULL status report
    and stores it as the baseline.
  * Every later run: emails only the CHANGES (newly available / no longer available)
    versus the stored baseline. No change -> no email.

Config via env vars (all optional): STATE_FILE, DRY_RUN, plus the GMAIL_* / ALERT_TO
used by notify.py.
"""

import argparse
import json
import os
import sys
import time
import datetime
import pathlib

# Robust stdout for non-ASCII on Windows consoles (cp1252) and CI alike.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import checker
import notify

STATE_FILE = pathlib.Path(os.environ.get("STATE_FILE", "state.json"))
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
SINGLE_DIGITS = [str(d) for d in range(1, 10)]

FAMILIES = [
    {"key": "FS-??-1", "label": "FS ?? 1  (any two letters, number 1)", "mode": "letters", "number": "1"},
    {"key": "FS-SK-?", "label": "FS SK ?  (single-digit number)",       "mode": "numbers", "letters": "SK"},
    {"key": "FS-KH-?", "label": "FS KH ?  (single-digit number)",       "mode": "numbers", "letters": "KH"},
    {"key": "FS-ST-?", "label": "FS ST ?  (single-digit number)",       "mode": "numbers", "letters": "ST"},
    {"key": "FS-KO-?", "label": "FS KO ?  (single-digit number)",       "mode": "numbers", "letters": "KO"},
    {"key": "FS-RT-?", "label": "FS RT ?  (single-digit number)",       "mode": "numbers", "letters": "RT"},
    {"key": "FS-OO-?", "label": "FS OO ?  (single-digit number)",       "mode": "numbers", "letters": "OO"},
    {"key": "FS-ZZ-?", "label": "FS ZZ ?  (single-digit number)",       "mode": "numbers", "letters": "ZZ"},
    {"key": "FS-YY-?", "label": "FS YY ?  (single-digit number)",       "mode": "numbers", "letters": "YY"},
    {"key": "FS-XX-?", "label": "FS XX ?  (single-digit number)",       "mode": "numbers", "letters": "XX"},
]


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"initialized": False, "families": {}, "last_run": None, "runs": 0}


def save_state(families, initialized):
    prev = load_state()
    STATE_FILE.write_text(json.dumps({
        "initialized": initialized,
        "families": families,
        "last_run": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "runs": prev.get("runs", 0) + 1,
    }, indent=2), encoding="utf-8")


def _num_of(plate):
    return int(plate.rsplit("-", 1)[1])


def sweep():
    """Return {family_key: sorted[plate strings]} or None if any query failed/blocked."""
    session = checker.new_session()
    result = {}
    for fam in FAMILIES:
        try:
            if fam["mode"] == "letters":
                pairs = checker.available_letters(fam["number"], session=session)
                plates = sorted(f"FS-{p}-{fam['number']}" for p in pairs)
            else:  # numbers, single-digit only
                nums = [n for n in checker.available_numbers(fam["letters"], session=session)
                        if n in SINGLE_DIGITS]
                plates = sorted((f"FS-{fam['letters']}-{n}" for n in nums), key=_num_of)
            result[fam["key"]] = plates
            print(f"  {fam['key']}: {len(plates)} available -> {plates if plates else '—'}", flush=True)
        except checker.Blocked as e:
            print(f"  ! blocked: {e} — sweep inconclusive, state untouched.", flush=True)
            return None
        except Exception as e:  # noqa: BLE001
            print(f"  ! error on {fam['key']}: {e} — sweep inconclusive, state untouched.", flush=True)
            return None
        time.sleep(1.0)  # tiny courtesy gap between the 3 requests
    return result


def build_report_snapshot(current):
    snap = []
    for fam in FAMILIES:
        avail = current.get(fam["key"], [])
        entry = {"label": fam["label"], "mode": fam["mode"], "available": avail, "taken_single": None}
        if fam["mode"] == "numbers":
            free = {_num_of(p) for p in avail}
            entry["taken_single"] = [f"FS-{fam['letters']}-{d}" for d in range(1, 10) if d not in free]
        snap.append(entry)
    return snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="force a full status report email + re-baseline")
    ap.add_argument("--dry-run", action="store_true", help="never send email; just print")
    ap.add_argument("--test-email", action="store_true", help="send a credentials test email and exit")
    args = ap.parse_args()

    if args.test_email:
        notify.send_test()
        return

    dry = DRY_RUN or args.dry_run
    print(f"=== FS plate watch === {datetime.datetime.now().isoformat(timespec='seconds')} (dry_run={dry})")

    state = load_state()
    prev = state.get("families", {})
    current = sweep()
    if current is None:
        sys.exit(0)  # inconclusive; leave state alone

    want_report = args.report or not state.get("initialized")

    if want_report:
        print("Sending FULL status report (baseline).")
        snap = build_report_snapshot(current)
        if dry:
            for s in snap:
                print(f"  [{s['label']}] available={s['available']} taken_single={s['taken_single']}")
            print("(dry-run: report email NOT sent, state NOT saved)")
        else:
            notify.send_report(snap)
            save_state(current, initialized=True)
        return

    # Change mode: diff each family vs baseline.
    changes = []
    for fam in FAMILIES:
        cur = set(current.get(fam["key"], []))
        old = set(prev.get(fam["key"], []))
        new = sorted(cur - old, key=lambda p: (len(p), p))
        gone = sorted(old - cur, key=lambda p: (len(p), p))
        if new or gone:
            changes.append({"label": fam["label"], "new": new, "gone": gone})
            print(f"  CHANGE {fam['key']}: new={new} gone={gone}")

    if changes:
        if dry:
            print("(dry-run: change email NOT sent)")
        else:
            notify.send_changes(changes)
    else:
        print("No changes since last run.")

    if not dry:
        save_state(current, initialized=True)


if __name__ == "__main__":
    main()
