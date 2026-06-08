"""Offline tests for the 3-family watch: sweep, single-digit filter, report vs change
logic, and email formatting. Network + SMTP are stubbed — no real calls, no credentials.
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

import monitor  # noqa: E402
import notify   # noqa: E402

# --- stub the network: KO has single-digit 4,5,6,8,9 free; RT none; FS-AB-1 free ---
KO_NUMS = ["4", "5", "6", "8", "9", "10", "246"]
RT_NUMS = ["13", "20"]
monitor.checker.available_letters = lambda numbers, session=None: ["AB"]
monitor.checker.available_numbers = lambda letters, session=None: {"KO": KO_NUMS, "RT": RT_NUMS}.get(letters, [])

# --- capture emails instead of sending (keep originals for the formatting test) ---
_real_report = notify.send_report
_real_changes = notify.send_changes
sent = []
monitor.notify.send_report = lambda snap: sent.append(("report", snap))
monitor.notify.send_changes = lambda ch: sent.append(("changes", ch))


def run(argv):
    sys.argv = ["monitor"] + argv
    try:
        monitor.main()
    except SystemExit:
        pass


def test_sweep_and_single_digit_filter():
    cur = monitor.sweep()
    assert cur["FS-??-1"] == ["FS-AB-1"], cur["FS-??-1"]
    assert cur["FS-KO-?"] == ["FS-KO-4", "FS-KO-5", "FS-KO-6", "FS-KO-8", "FS-KO-9"], cur["FS-KO-?"]
    assert cur["FS-RT-?"] == [], cur["FS-RT-?"]  # 13,20 are not single-digit
    print("sweep + single-digit filter OK:", cur)


def test_report_then_changes():
    sent.clear()
    # Run 1: no baseline -> full report
    run([])
    assert sent and sent[-1][0] == "report", sent
    snap = {s["label"][:5]: s for s in sent[-1][1]}
    ko = next(s for s in sent[-1][1] if s["label"].startswith("FS KO"))
    assert ko["taken_single"] == ["FS-KO-1", "FS-KO-2", "FS-KO-3", "FS-KO-7"], ko["taken_single"]
    rt = next(s for s in sent[-1][1] if s["label"].startswith("FS RT"))
    assert rt["taken_single"] == [f"FS-RT-{d}" for d in range(1, 10)], rt["taken_single"]
    print("Run 1 OK: report sent; KO taken =", ko["taken_single"])

    # Run 2: identical data -> NO email
    sent.clear()
    run([])
    assert sent == [], sent
    print("Run 2 OK: no change -> no email")

    # Run 3: KO-7 frees up, KO-4 gets taken -> change email
    global KO_NUMS
    KO_NUMS = ["5", "6", "7", "8", "9"]
    sent.clear()
    run([])
    assert sent and sent[-1][0] == "changes", sent
    ch = next(c for c in sent[-1][1] if c["label"].startswith("FS KO"))
    assert ch["new"] == ["FS-KO-7"], ch["new"]
    assert ch["gone"] == ["FS-KO-4"], ch["gone"]
    print("Run 3 OK: change detected new =", ch["new"], "gone =", ch["gone"])


def test_email_formatting():
    notify.send_report = _real_report      # undo the capture stubs for real formatting
    notify.send_changes = _real_changes
    captured = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, p): pass
        def send_message(self, msg):
            captured["subject"] = msg["Subject"]
            captured["to"] = msg["To"]
            captured["body"] = msg.get_content()

    notify.smtplib.SMTP_SSL = lambda *a, **k: FakeSMTP()
    notify.send_report([
        {"label": "FS ?? 1", "mode": "letters", "available": [], "taken_single": None},
        {"label": "FS KO ?", "mode": "numbers", "available": ["FS-KO-4"], "taken_single": ["FS-KO-1"]},
    ])
    assert captured["to"] == "stephan.kohlhaas@tum.de", captured
    assert "FS-KO-4" in captured["body"] and "FS-KO-1" in captured["body"]
    assert "buergerserviceportal" in captured["body"]
    print("report email OK:", captured["subject"])

    notify.send_changes([{"label": "FS ?? 1", "new": ["FS-SK-1"], "gone": []}])
    assert "FS-SK-1" in captured["body"]
    assert "newly available" in captured["subject"]
    print("change email OK:", captured["subject"])


if __name__ == "__main__":
    test_sweep_and_single_digit_filter()
    test_report_then_changes()
    test_email_formatting()
    os.unlink(_tmp.name)
    print("\nALL TESTS PASSED")
