"""Availability checker against the confirmed live endpoint.

Endpoint (reverse-engineered from the official Freising checker on
wunschkennzeichen-reservieren.jetzt, which queries the authority's i-Kfz system):

  POST https://backend.wunschkennzeichen-reservieren.jetzt/reservation-checks
  body: {"plateQuery": {... city/letters/numbers ...}, "officeId": "<Freising>", ...}
  ->    {... "isAvailable": <bool>, "plates": [<available plates>] ...}

No authentication, no browser, no special headers required (verified).
"""

import datetime
import time
import random

import requests

ENDPOINT = "https://backend.wunschkennzeichen-reservieren.jetzt/reservation-checks"
OFFICE_ID = "5f17f89ddff4262e1b32f4ed"          # Landkreis Freising (i-Kfz key 09178000)
SITE = "https://wunschkennzeichen-reservieren.jetzt"
# The official portal where the user actually reserves once a plate is free:
RESERVE_URL = "https://www.buergerserviceportal.de/bayern/lkrfreising/igvwkz"

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class Blocked(Exception):
    """Raised when the backend rate-limits / blocks us (HTTP 403/429)."""


def new_session():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": SITE,
        "Referer": f"{SITE}/freising/reservieren",
        "User-Agent": DEFAULT_UA,
    })
    return s


def _payload(letters, numbers):
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
        "timestamp": datetime.datetime.now(datetime.timezone.utc)
        .isoformat().replace("+00:00", "Z"),
        "loadingValue": 2,
    }


def available_numbers(letters, session=None, retries=3):
    """Return the sorted list of ALL currently-available numbers for FS-<letters>-?.

    One request: an empty `numbers` with suggestionMethod 'all' makes the backend
    enumerate every free number for that letter pair (e.g. ['4','5','6','8',...]).
    Raises Blocked on 403/429; retries transient errors.
    """
    sess = session or new_session()
    last_err = None
    for attempt in range(retries):
        try:
            r = sess.post(ENDPOINT, json=_payload(letters, ""), timeout=25)
            if r.status_code in (403, 429):
                raise Blocked(f"HTTP {r.status_code} for FS-{letters}-?")
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            data = r.json()
            nums = [str(p.get("numbers")) for p in (data.get("plates") or []) if p.get("numbers")]
            return sorted(set(nums), key=lambda n: int(n))
        except Blocked:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1) + random.uniform(0, 0.5))
    raise RuntimeError(f"available_numbers failed for FS-{letters}-?: {last_err}")


def available_letters(numbers, session=None, retries=3):
    """Return the sorted list of available LETTER pairs for FS-?-<numbers> (one request).

    Mirror of available_numbers: an empty `letters` enumerates every free letter pair
    for the given number (e.g. numbers='1' -> the letter pairs whose 'number 1' plate is
    free). Note: the backend's suggestion list appears to cap at ~96 entries, which is
    irrelevant for coveted single-digit numbers (only a handful are ever free at once).
    Raises Blocked on 403/429; retries transient errors.
    """
    sess = session or new_session()
    last_err = None
    for attempt in range(retries):
        try:
            r = sess.post(ENDPOINT, json=_payload("", numbers), timeout=25)
            if r.status_code in (403, 429):
                raise Blocked(f"HTTP {r.status_code} for FS-?-{numbers}")
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            data = r.json()
            pairs = [str(p.get("letters")) for p in (data.get("plates") or []) if p.get("letters")]
            return sorted(set(pairs))
        except Blocked:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1) + random.uniform(0, 0.5))
    raise RuntimeError(f"available_letters failed for FS-?-{numbers}: {last_err}")


def check_plate(letters, numbers="1", session=None, retries=3):
    """Return (available: bool, plates: list[dict]) for FS-<letters>-<numbers>.

    Raises Blocked on 403/429. Retries transient errors (timeouts, 5xx) with backoff.
    """
    sess = session or new_session()
    last_err = None
    for attempt in range(retries):
        try:
            r = sess.post(ENDPOINT, json=_payload(letters, numbers), timeout=20)
            if r.status_code in (403, 429):
                raise Blocked(f"HTTP {r.status_code} for FS-{letters}-{numbers}")
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            data = r.json()
            return bool(data.get("isAvailable")), data.get("plates") or []
        except Blocked:
            raise
        except Exception as e:  # noqa: BLE001 - transient network/5xx
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1) + random.uniform(0, 0.5))
    raise RuntimeError(f"check_plate failed for FS-{letters}-{numbers}: {last_err}")


if __name__ == "__main__":
    s = new_session()
    for letters, num in [("XY", "1"), ("JW", "246")]:
        avail, plates = check_plate(letters, num, session=s)
        print(f"FS-{letters}-{num}: available={avail} plates={plates}")
