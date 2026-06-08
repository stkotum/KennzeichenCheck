"""Generate every valid Freising (FS) Wunschkennzeichen of the form FS-<two letters>-1.

Rules confirmed for the Freising registration district (Zulassungsbezirk FS):
  * Format used here: 2 letters + 1 digit  (e.g. FS-AB-1). This is the shortest
    legal form that ends in the single digit "1".
  * Allowed letters: A-Z, EXCEPT I, O, Q (excluded to avoid confusion with 1/0).
  * Forbidden letter pairs (nationwide, historical/political): HJ, KZ, NS, SA, SS.
  * The trailing number is fixed to 1 (that is the plate the user wants).
"""

EXCLUDED_LETTERS = {"I", "O", "Q"}
FORBIDDEN_PAIRS = {"HJ", "KZ", "NS", "SA", "SS"}
DISTRICT = "FS"
NUMBER = "1"

ALLOWED_LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1) if chr(c) not in EXCLUDED_LETTERS]


def valid_letter_pairs():
    """Yield every allowed two-letter combination (excluding forbidden pairs)."""
    for a in ALLOWED_LETTERS:
        for b in ALLOWED_LETTERS:
            pair = a + b
            if pair in FORBIDDEN_PAIRS:
                continue
            yield pair


def all_plates():
    """Return the full list of plate dicts to monitor, e.g. {'letters': 'AB', 'number': '1'}."""
    return [{"district": DISTRICT, "letters": p, "number": NUMBER} for p in valid_letter_pairs()]


def plate_str(plate, sep="-"):
    """Human/URL friendly string: FS-AB-1."""
    return f"{plate['district']}{sep}{plate['letters']}{sep}{plate['number']}"


if __name__ == "__main__":
    plates = all_plates()
    print(f"Allowed letters ({len(ALLOWED_LETTERS)}): {''.join(ALLOWED_LETTERS)}")
    print(f"Total valid FS-??-1 plates to monitor: {len(plates)}")
    print("First 5:", [plate_str(p) for p in plates[:5]])
    print("Last 5: ", [plate_str(p) for p in plates[-5:]])
    for bad in FORBIDDEN_PAIRS:
        assert all(p["letters"] != bad for p in plates), f"{bad} leaked in!"
    print("Forbidden pairs correctly excluded:", sorted(FORBIDDEN_PAIRS))
