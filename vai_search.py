"""STANDALONE one-off search (does NOT touch the FS watcher).

Find which VAI-??-{NUMBER} plates (Vaihingen an der Enz, any two letters + number 1) are
available, and recommend pairs that fit "Patrick Vier".

VAI is an 'intelliform' office: the letters-wildcard enumeration does NOT work and
number-suggestions are only a partial sample, so we must check each letter pair
individually (one request per pair).
"""

import datetime
import string
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

ENDPOINT = "https://backend.wunschkennzeichen-reservieren.jetzt/reservation-checks"
VAI_OFFICE = "5f17f89ddff4262e1b32f6e1"        # Vaihingen an der Enz (codes LB/VAI)
NUMBER = sys.argv[1] if len(sys.argv) > 1 else "1"   # end number, e.g. `python vai_search.py 4`

# Nationwide forbidden 2-letter combos; I/Q are not used as plate letters.
FORBIDDEN_PAIRS = {"HJ", "KZ", "NS", "SA", "SS"}
LETTERS = [c for c in string.ascii_uppercase if c not in {"I", "Q"}]

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})


def _payload(letters):
    return {
        "plateQuery": {"suggestionMethod": "all", "city": "VAI", "letters": letters,
                       "numbers": NUMBER, "option": "standard", "vehicle": "car",
                       "seasonFrom": 4, "seasonTo": 10, "size": "520x110"},
        "plates": [], "status": "loading", "officeId": VAI_OFFICE,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "loadingValue": 2,
    }


def is_available(letters):
    for _ in range(3):
        try:
            r = SESSION.post(ENDPOINT, json=_payload(letters), timeout=25)
            if r.status_code < 500:
                return letters, bool(r.json().get("isAvailable"))
        except Exception:
            pass
    return letters, None  # unknown after retries


def fit_score(pair):
    """How well does VAI-<pair>-1 fit 'Patrick Vier'? Higher = better."""
    a, b = pair[0], pair[1]
    if pair in ("PV", "VP"):
        return (100, "initials Patrick Vier")
    notes = []
    score = 0
    if pair == "VI":
        score += 70; notes.append("'VI' ~ Vier / echoes the VAI district")
    if pair in ("PA", "PT", "PK", "PI"):
        score += 55; notes.append("starts the name Patrick")
    if pair in ("VR", "VE"):
        score += 55; notes.append("'V' + Vier")
    if a == "P" and b == "V":
        score += 100
    if a in ("P", "V") and b in ("P", "V"):
        score += 60; notes.append("both initials P/V")
    if a in ("P", "V") or b in ("P", "V"):
        score += 25; notes.append(f"contains his initial {a if a in 'PV' else b}")
    if a == b:
        score += 10; notes.append("nice repeated letters")
    return (score, "; ".join(notes) or "available")


def main():
    pairs = [a + b for a in LETTERS for b in LETTERS if (a + b) not in FORBIDDEN_PAIRS]
    print(f"Checking {len(pairs)} VAI-??-{NUMBER} letter pairs ...", flush=True)

    available = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for letters, ok in ex.map(is_available, pairs):
            if ok:
                available.append(letters)

    available.sort()
    print(f"\n=== AVAILABLE VAI-??-{NUMBER} : {len(available)} ===")
    print(", ".join(f"VAI-{p}-{NUMBER}" for p in available) if available else "(none)")

    ranked = sorted(((fit_score(p), p) for p in available), key=lambda x: -x[0][0])
    print("\n=== BEST FITS FOR PATRICK VIER (available now) ===")
    shown = 0
    for (score, why), p in ranked:
        if score <= 0:
            continue
        print(f"  VAI-{p}-{NUMBER}   (score {score}) - {why}")
        shown += 1
        if shown >= 15:
            break
    if shown == 0:
        print("  none of the available pairs map to his name; top available overall:",
              ", ".join(f"VAI-{p}-{NUMBER}" for p in available[:15]))


if __name__ == "__main__":
    main()
