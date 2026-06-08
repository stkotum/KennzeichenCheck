"""Confirm the availability endpoint works with plain HTTP (no browser).

If this works, the production bot needs only `requests` — no Playwright/Chromium.
Tests a few combos + checks whether browser-like headers are required.
"""

import json
import datetime
import requests

ENDPOINT = "https://backend.wunschkennzeichen-reservieren.jetzt/reservation-checks"
OFFICE_ID = "5f17f89ddff4262e1b32f4ed"  # Freising (ikfzKey 09178000), from scout
SITE = "https://wunschkennzeichen-reservieren.jetzt"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": SITE,
    "Referer": f"{SITE}/freising/reservieren",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}


def build_payload(letters, numbers="1"):
    return {
        "plateQuery": {
            "suggestionMethod": "all",
            "city": "FS",
            "letters": letters,
            "numbers": numbers,
            "option": "standard",
            "vehicle": "car",
            "seasonFrom": 4,
            "seasonTo": 10,
            "size": "520x110",
        },
        "plates": [],
        "status": "loading",
        "officeId": OFFICE_ID,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "loadingValue": 2,
    }


def check(letters, numbers="1", headers=HEADERS):
    r = requests.post(ENDPOINT, json=build_payload(letters, numbers), headers=headers, timeout=20)
    out = {"status": r.status_code}
    try:
        data = r.json()
        out["isAvailable"] = data.get("isAvailable")
        out["state"] = data.get("state")
        out["plates"] = data.get("plates")
    except Exception:
        out["text"] = r.text[:300]
    return out


if __name__ == "__main__":
    # 1) Reproduce the scout result (XY 1 -> expected isAvailable False)
    print("FS-XY-1 (with browser-like headers):", check("XY"))

    # 2) Does it work with NO special headers (bare requests)?
    print("FS-XY-1 (bare, no headers):       ", check("XY", headers={"Content-Type": "application/json"}))

    # 3) A spread of real candidates to see if any '1' plate is currently free
    for letters in ["AB", "SK", "ST", "KO", "MM", "ZZ", "BW", "WX", "VV", "TT"]:
        print(f"FS-{letters}-1:", check(letters))
