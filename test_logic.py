"""Offline tests: multi-district sweep, single-digit filter, per-audience routing
(Emil gets ES/NT only; owner gets everything), and email formatting. Network + SMTP
stubbed -- no real calls, no credentials.
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

# ---- stub the network (mutable globals so we can simulate changes) ----
KO = ["4", "5", "12"]          # FS-KO single-digit -> 4,5 (12 filtered out)
NTHN = {"6", "9"}              # NT-HN single-digit available

monitor.checker.available_letters = lambda numbers, session=None, city="FS", office_id=None: []
monitor.checker.available_numbers = lambda letters, session=None, city="FS", office_id=None: (KO if letters == "KO" else [])
monitor.checker.check_plate = lambda letters, numbers, session=None, city="FS", office_id=None: (
    (city == "NT" and letters == "HN" and numbers in NTHN), [])
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


def test_report_routing():
    sent.clear()
    run()  # state uninitialised -> full report to each audience
    by = {rec: snap for kind, rec, snap in sent if kind == "report"}
    assert set(by) == {OWNER, EMIL}, list(by)
    assert len(by[OWNER]) == 16, len(by[OWNER])                 # 10 FS + 6 ES/NT
    assert len(by[EMIL]) == 6, len(by[EMIL])                    # ES/NT only
    assert all(s["label"][:2] in ("ES", "NT") for s in by[EMIL]), [s["label"] for s in by[EMIL]]
    ko = next(s for s in by[OWNER] if s["label"].startswith("FS KO"))
    assert ko["available"] == ["FS-KO-4", "FS-KO-5"], ko["available"]
    nthn = next(s for s in by[OWNER] if s["label"].startswith("NT HN"))
    assert nthn["available"] == ["NT-HN-6", "NT-HN-9"], nthn["available"]
    print("report routing OK: owner=16 fams, emil=6 (ES/NT only)")


def test_esnt_change_goes_to_both():
    global NTHN
    NTHN = {"7", "9"}            # NT-HN-7 newly available, NT-HN-6 gone
    sent.clear()
    run()
    chg = {rec: ch for kind, rec, ch in sent if kind == "changes"}
    assert set(chg) == {OWNER, EMIL}, list(chg)                 # ES/NT change -> both
    for rec in (OWNER, EMIL):
        hn = next(c for c in chg[rec] if c["label"].startswith("NT HN"))
        assert hn["new"] == ["NT-HN-7"] and hn["gone"] == ["NT-HN-6"], hn
    print("ES/NT change routing OK: owner + Emil both notified")


def test_fs_change_excludes_emil():
    global KO
    KO = ["4", "5", "6", "12"]   # FS-KO-6 newly available; no ES/NT change
    sent.clear()
    run()
    recs = {rec for kind, rec, ch in sent if kind == "changes"}
    assert OWNER in recs and EMIL not in recs, recs               # FS-only -> owner only
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
    notify.send_changes([{"label": "NT HN ?", "new": ["NT-HN-7"], "gone": []}], list(EMIL))
    assert cap["to"] == "emil.hennrich@gmx.net", cap["to"]
    assert cap["subject"].startswith("ALERT") and "newly available" in cap["subject"]
    assert "NT-HN-7" in cap["body"]
    cap["subject"].encode("ascii"); cap["body"].encode("ascii")   # must be emoji-free
    print("email formatting OK:", cap["subject"], "->", cap["to"])


if __name__ == "__main__":
    test_report_routing()
    test_esnt_change_goes_to_both()
    test_fs_change_excludes_emil()
    test_email_formatting()
    os.unlink(_tmp.name)
    print("\nALL TESTS PASSED")
