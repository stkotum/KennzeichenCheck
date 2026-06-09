"""Standalone one-off lookup (does NOT touch the FS watcher).

For districts ES (Esslingen) and NT (Nuertingen), check single-digit (1-9) availability
of the letter pairs AZ, EH, HN -> e.g. ES-AZ-1 ... ES-AZ-9.
"""

import datetime
import re
import requests

EP = "https://backend.wunschkennzeichen-reservieren.jetzt/reservation-checks"
BASE = "https://wunschkennzeichen-reservieren.jetzt"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
S = requests.Session(); S.headers.update({"Content-Type": "application/json"})

PAIRS = ["AZ", "EH", "HN"]
DISTRICTS = [("ES", ["esslingen", "esslingen-am-neckar"]),
             ("NT", ["nuertingen", "nurtingen"])]


def payload(city, letters, numbers, oid):
    return {"plateQuery": {"suggestionMethod": "all", "city": city, "letters": letters,
            "numbers": numbers, "option": "standard", "vehicle": "car", "seasonFrom": 4,
            "seasonTo": 10, "size": "520x110"}, "plates": [], "status": "loading",
            "officeId": oid, "timestamp": datetime.datetime.now(datetime.timezone.utc)
            .isoformat().replace("+00:00", "Z"), "loadingValue": 2}


def office_for(oid, city):
    d = S.post(EP, json=payload(city, "AZ", "1", oid), timeout=25).json()
    return d.get("office") or {}


def find_office(code, slugs):
    """Return (officeId, slug, abbreviations) for a district code, or None."""
    for slug in slugs:
        r = requests.get(f"{BASE}/{slug}/reservieren", headers=H, timeout=25)
        if r.status_code != 200:
            continue
        txt = r.text
        # collect 24-hex ids appearing shortly before each occurrence of the quoted slug
        cands = []
        for m in re.finditer(re.escape(f'"{slug}"'), txt):
            window = txt[max(0, m.start() - 200):m.start()]
            cands += re.findall(r"[0-9a-f]{24}", window)
        for cand in dict.fromkeys(reversed(cands)):      # nearest first
            off = office_for(cand, code)
            abbr = (off.get("reservation") or {}).get("cityAbbreviations") or []
            if off.get("slug") == slug and code in abbr:
                return cand, slug, abbr
    return None


def check(oid, city, letters, number):
    d = S.post(EP, json=payload(city, letters, number, oid), timeout=25).json()
    return bool(d.get("isAvailable"))


def main():
    for code, slugs in DISTRICTS:
        found = find_office(code, slugs)
        print(f"\n========== {code} ==========")
        if not found:
            print(f"  could not resolve office for {code} (tried slugs {slugs})")
            continue
        oid, slug, abbr = found
        print(f"  office: slug={slug} id={oid} codes={abbr}")
        for pair in PAIRS:
            free = [str(d) for d in range(1, 10) if check(oid, code, pair, str(d))]
            label = ", ".join(f"{code}-{pair}-{d}" for d in free) if free else "none"
            print(f"  {code}-{pair}-?  single-digit available: {label}")


if __name__ == "__main__":
    main()
