"""Watch FS + ES/NT Wunschkennzeichen queries and email on changes.

Districts / offices:
  FS (Freising)            office 5f17f89ddff4262e1b32f4ed  (i-Kfz; wildcard enumeration works)
  ES (Esslingen)           office 5f17f89ddff4262e1b32f4da  (per-digit probe)
  NT (Nuertingen)          office 5f17f89ddff4262e1b32f62a  (per-digit probe)

Recipients (per group):
  FS plates   -> owner only            (stephan.kohlhaas@tum.de, stkotum@gmail.com)
  ES/NT plates-> owner + Emil Hennrich (emil.hennrich@gmx.net)

First run (state not initialised) OR --report: emails a FULL status report (current
availability) to each audience. Every later run: emails only CHANGES, subject 'ALERT:'.
Every family watches number 1 only: FS-SK-1 and ES/NT-AZ/EH/HN-1.
"""

import argparse
import json
import os
import sys
import time
import datetime
import pathlib

for _stream in (sys.stdout, sys.stderr):       # robust non-ASCII on Windows / CI
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import checker
import notify

STATE_FILE = pathlib.Path(os.environ.get("STATE_FILE", "state.json"))
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
SINGLE_DIGITS = [str(d) for d in range(1, 10)]

FS_OFFICE = "5f17f89ddff4262e1b32f4ed"
ES_OFFICE = "5f17f89ddff4262e1b32f4da"
NT_OFFICE = "5f17f89ddff4262e1b32f62a"


def _fam(key, label, group, mode, city, office, **kw):
    return {"key": key, "label": label, "group": group, "mode": mode,
            "city": city, "office": office, **kw}


FAMILIES = [
    # --- Freising (owner only) -- NUMBER 1 ONLY --------------------------------
    _fam("FS-SK-1", "FS SK 1  (number 1)", "FS", "numbers", "FS", FS_OFFICE, letters="SK", numbers=["1"]),
    # --- Esslingen + Nuertingen (owner + Emil) -- NUMBER 1 ONLY -----------------
    _fam("ES-AZ-1", "ES AZ 1  (number 1)", "ESNT", "digits", "ES", ES_OFFICE, letters="AZ", digits=["1"]),
    _fam("ES-EH-1", "ES EH 1  (number 1)", "ESNT", "digits", "ES", ES_OFFICE, letters="EH", digits=["1"]),
    _fam("ES-HN-1", "ES HN 1  (number 1)", "ESNT", "digits", "ES", ES_OFFICE, letters="HN", digits=["1"]),
    _fam("NT-AZ-1", "NT AZ 1  (number 1)", "ESNT", "digits", "NT", NT_OFFICE, letters="AZ", digits=["1"]),
    _fam("NT-EH-1", "NT EH 1  (number 1)", "ESNT", "digits", "NT", NT_OFFICE, letters="EH", digits=["1"]),
    _fam("NT-HN-1", "NT HN 1  (number 1)", "ESNT", "digits", "NT", NT_OFFICE, letters="HN", digits=["1"]),
]

OWNER = ["stephan.kohlhaas@tum.de", "stkotum@gmail.com"]
EMIL = ["emil.hennrich@gmx.net"]
AUDIENCES = [
    {"name": "owner", "recipients": OWNER, "groups": {"FS", "ESNT"}},   # everything
    {"name": "emil", "recipients": EMIL, "groups": {"ESNT"}},           # ES/NT only
]


def _num_of(plate):
    return int(plate.rsplit("-", 1)[1])


def _watched(fam):
    """Digits a numbers/digits family watches; default: every single digit."""
    return fam.get("digits" if fam["mode"] == "digits" else "numbers", SINGLE_DIGITS)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"initialized": False, "families": {}, "last_run": None, "runs": 0}


def save_state(families):
    prev = load_state()
    STATE_FILE.write_text(json.dumps({
        "initialized": True, "families": families,
        "last_run": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "runs": prev.get("runs", 0) + 1,
    }, indent=2), encoding="utf-8")


def _family_available(fam, session):
    c, o = fam["city"], fam["office"]
    if fam["mode"] == "letters":
        pairs = checker.available_letters(fam["number"], session=session, city=c, office_id=o)
        return sorted(f"{c}-{p}-{fam['number']}" for p in pairs)
    if fam["mode"] == "numbers":          # ikfz wildcard, keep only watched digits
        watched = _watched(fam)
        nums = [n for n in checker.available_numbers(fam["letters"], session=session, city=c, office_id=o)
                if n in watched]
        return sorted((f"{c}-{fam['letters']}-{n}" for n in nums), key=_num_of)
    if fam["mode"] == "digits":           # per-digit probe (intelliform offices)
        free = []
        for d in _watched(fam):
            ok, _ = checker.check_plate(fam["letters"], d, session=session, city=c, office_id=o)
            if ok:
                free.append(d)
            time.sleep(0.3)
        return sorted((f"{c}-{fam['letters']}-{d}" for d in free), key=_num_of)
    raise ValueError(fam["mode"])


def sweep():
    session = checker.new_session()
    result = {}
    for fam in FAMILIES:
        try:
            plates = _family_available(fam, session)
            result[fam["key"]] = plates
            print(f"  {fam['key']}: {len(plates)} available -> {plates if plates else '-'}", flush=True)
        except checker.Blocked as e:
            print(f"  ! blocked: {e} -- sweep inconclusive, state untouched.", flush=True)
            return None
        except Exception as e:  # noqa: BLE001
            print(f"  ! error on {fam['key']}: {e} -- sweep inconclusive, state untouched.", flush=True)
            return None
        time.sleep(0.6)
    return result


def snapshot_for(current, fams):
    snap = []
    for fam in fams:
        avail = current.get(fam["key"], [])
        entry = {"label": fam["label"], "available": avail, "taken_single": None}
        if fam["mode"] in ("numbers", "digits"):
            watched = [int(d) for d in _watched(fam)]
            free = {_num_of(p) for p in avail}
            entry["taken_single"] = [f"{fam['city']}-{fam['letters']}-{d}" for d in watched if d not in free]
        snap.append(entry)
    return snap


def changes_for(current, prev, fams):
    out = []
    for fam in fams:
        cur = set(current.get(fam["key"], []))
        old = set(prev.get(fam["key"], []))
        new = sorted(cur - old, key=lambda p: (len(p), p))
        gone = sorted(old - cur, key=lambda p: (len(p), p))
        if new or gone:
            out.append({"label": fam["label"], "new": new, "gone": gone})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="force a full status report + re-baseline")
    ap.add_argument("--dry-run", action="store_true", help="never send email; just print")
    ap.add_argument("--test-email", action="store_true", help="send a credentials test to the owner and exit")
    ap.add_argument("--silent-baseline", action="store_true", help="sweep and save state as baseline WITHOUT emailing")
    args = ap.parse_args()

    if args.test_email:
        notify.send_test(OWNER)
        return

    dry = DRY_RUN or args.dry_run
    print(f"=== Kennzeichen watch === {datetime.datetime.now().isoformat(timespec='seconds')} (dry_run={dry})")

    state = load_state()
    prev = state.get("families", {})
    current = sweep()
    if current is None:
        sys.exit(0)

    if args.silent_baseline:
        save_state(current)
        print("Silent baseline saved (no email).")
        return

    want_report = args.report or not state.get("initialized")

    for aud in AUDIENCES:
        fams = [f for f in FAMILIES if f["group"] in aud["groups"]]
        if want_report:
            snap = snapshot_for(current, fams)
            print(f"[{aud['name']}] full report -> {aud['recipients']}")
            if not dry:
                notify.send_report(snap, aud["recipients"])
        else:
            ch = changes_for(current, prev, fams)
            if ch:
                print(f"[{aud['name']}] {len(ch)} changed families -> {aud['recipients']}")
                if not dry:
                    notify.send_changes(ch, aud["recipients"])
            else:
                print(f"[{aud['name']}] no changes")

    if not dry:
        save_state(current)
    else:
        print("(dry-run: no email sent, state NOT saved)")


if __name__ == "__main__":
    main()
