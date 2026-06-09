"""Availability checker against the live endpoint, for ANY district/office.

  POST https://backend.wunschkennzeichen-reservieren.jetzt/reservation-checks
  body: {"plateQuery": {city/letters/numbers ...}, "officeId": "<office>", ...}
  ->    {... "isAvailable": <bool>, "plates": [<available plates>] ...}

No authentication / browser needed. City + officeId default to Freising so existing
FS calls keep working unchanged; pass city/office_id for other districts.
"""

import datetime
import time
import random

import requests

ENDPOINT = "https://backend.wunschkennzeichen-reservieren.jetzt/reservation-checks"
FS_OFFICE = "5f17f89ddff4262e1b32f4ed"          # Landkreis Freising (i-Kfz key 09178000)
SITE = "https://wunschkennzeichen-reservieren.jetzt"

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


def _payload(letters, numbers, city="FS", office_id=FS_OFFICE):
    return {
        "plateQuery": {
            "suggestionMethod": "all", "city": city, "letters": letters,
            "numbers": numbers, "option": "standard", "vehicle": "car",
            "seasonFrom": 4, "seasonTo": 10, "size": "520x110",
        },
        "plates": [], "status": "loading", "officeId": office_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc)
        .isoformat().replace("+00:00", "Z"),
        "loadingValue": 2,
    }


def _post(session, letters, numbers, city, office_id, retries, timeout=25):
    sess = session or new_session()
    last = None
    for attempt in range(retries):
        try:
            r = sess.post(ENDPOINT, json=_payload(letters, numbers, city, office_id), timeout=timeout)
            if r.status_code in (403, 429):
                raise Blocked(f"HTTP {r.status_code} for {city}-{letters}-{numbers}")
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            return r.json()
        except Blocked:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1) + random.uniform(0, 0.5))
    raise RuntimeError(f"request failed for {city}-{letters}-{numbers}: {last}")


def available_numbers(letters, session=None, retries=3, city="FS", office_id=FS_OFFICE):
    """All currently-available numbers for <city>-<letters>-? (one request, ikfz offices)."""
    data = _post(session, letters, "", city, office_id, retries)
    nums = [str(p.get("numbers")) for p in (data.get("plates") or []) if p.get("numbers")]
    return sorted(set(nums), key=lambda n: int(n))


def available_letters(numbers, session=None, retries=3, city="FS", office_id=FS_OFFICE):
    """All available letter pairs for <city>-?-<numbers> (one request, ikfz offices)."""
    data = _post(session, "", numbers, city, office_id, retries)
    pairs = [str(p.get("letters")) for p in (data.get("plates") or []) if p.get("letters")]
    return sorted(set(pairs))


def check_plate(letters, numbers="1", session=None, retries=3, city="FS", office_id=FS_OFFICE):
    """(available: bool, plates: list) for one specific <city>-<letters>-<numbers>.
    Works for every office type (use this for intelliform offices where wildcards fail)."""
    data = _post(session, letters, numbers, city, office_id, retries, timeout=20)
    return bool(data.get("isAvailable")), data.get("plates") or []


if __name__ == "__main__":
    s = new_session()
    print("FS-XY-1:", check_plate("XY", "1", session=s))
    print("NT-HN-9:", check_plate("HN", "9", session=s, city="NT", office_id="5f17f89ddff4262e1b32f62a"))
