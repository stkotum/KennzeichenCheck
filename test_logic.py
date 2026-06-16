"""Offline tests: multi-district sweep, FS single-digit + ES/NT number-1-only,
per-audience routing (Emil = ES/NT only), and email formatting. Network + SMTP stubbed.
Run: .venv/Scripts/python.exe test_logic.py
"""
import os
import sys
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
_tmp.close()
os.environ["STATE_FILE"] = _tmp.name
os.environ["GMAIL_USER"] = "test@example.com"
os.environ["GMAIL_APP_PASSWORD"] = "x" * 16

import monitor   # noqa: E402
import notify    # noqa: E402

KO = ["4", "5", "12"]        # FS-KO single-digit -> 4,5 (12 filtered)
HN1 = True                   # NT-HN-1 availability
esnt_digits_seen = []        # records which digits get probed for ES/NT

monitor.checker.available_letters = lambda numbers, session=None, city="FS", office_id=None: []
monitor.checker.available_numbers = lambda letters, session=None, city="FS", office_id=None: (KO if letters == "KO" else [])


def _check(letters, numbers, session=None, city="FS", office_id=None):
    if city in ("ES", "NT"):
        esnt_digits_seen.append(numbers)
    return (city == "NT" and letters == "HN" and numbers == "1" and HN1), []


monitor.checker.check_plate = _check
monitor.time.sleep = lambda *a, **k: None

_real_report, _real_changes = notify.send_report, notify.send_changes
sent = []
monitor.notify.send_report = lambda snap, rec: sent.append(("report", tuple(rec), snap))
monitor.notify.send_changes = lambda ch, rec: sent.append(("changes", tuple(rec), ch))

OWNER = ("stephan.kohlhaas@tum.de", "stkotum@gmail.com")
EMIL = ("emil.hennrich@gmx.net",)


def run():
    sys.argv = ["monitor"]
    monitor.main()


def test_report_routing_and_number1_only():
    sent.clear(); esnt_digits_seen.clear()
    run()
    assert set(esnt_digits_seen) == {"1"}, f"ES/NT must probe only digit 1, saw {set(esnt_digits_seen)}"
    by = {rec: snap for kind, rec, snap in sent if kind == "report"}
    assert set(by) == {OWNER, EMIL}, list(by)
    assert len(by[OWNER]) == 16 and len(by[EMIL]) == 6, (len(by[OWNER]), len(by[EMIL]))
    assert all(s["label"][:2] in ("ES", "NT") for s in by[EMIL])
    hn = next(s for s in by[EMIL] if s["label"].startswith("NT HN"))
    assert hn["available"] == ["NT-HN-1"], hn["available"]
    assert hn["taken_single"] == [], hn["taken_single"]   # only digit 1 watched, and it's free
    print("report routing + number-1-only OK")


def test_esnt_change_goes_to_both():
    global HN1
    HN1 = False                  # NT-HN-1 no longer available
    sent.clear()
    run()
    chg = {rec: ch for kind, rec, ch in sent if kind == "changes"}
    assert set(chg) == {OWNER, EMIL}, list(chg)
    for rec in (OWNER, EMIL):
        hn = next(c for c in chg[rec] if c["label"].startswith("NT HN"))
        assert hn["gone"] == ["NT-HN-1"] and hn["new"] == [], hn
    print("ES/NT change routing OK")


def test_fs_change_excludes_emil():
    global KO
    KO = ["4", "5", "6", "12"]    # FS-KO-6 new; no ES/NT change
    sent.clear()
    run()
    recs = {rec for kind, rec, ch in sent if kind == "changes"}
    assert OWNER in recs and EMIL not in recs, recs
    print("FS-only change routing OK: Emil NOT notified")


def test_email_formatting():
    notify.send_report, notify.send_changes = _real_report, _real_changes
    cap = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def send_message(self, m):
            cap["subject"], cap["to"], cap["body"] = m["Subject"], m["To"], m.get_content()

    notify.smtplib.SMTP_SSL = lambda *a, **k: FakeSMTP()
    notify.send_changes([{"label": "NT HN 1", "new": ["NT-HN-1"], "gone": []}], list(EMIL))
    assert cap["to"] == "emil.hennrich@gmx.net"
    assert cap["subject"].startswith("ALERT") and "newly available" in cap["subject"]
    cap["subject"].encode("ascii"); cap["body"].encode("ascii")
    print("email formatting OK:", cap["subject"], "->", cap["to"])


if __name__ == "__main__":
    test_report_routing_and_number1_only()
    test_esnt_change_goes_to_both()
    test_fs_change_excludes_emil()
    test_email_formatting()
    os.unlink(_tmp.name)
    print("\nALL TESTS PASSED")
