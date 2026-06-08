"""Email out: a full status report, a change alert, or a credentials test.

Credentials come from environment variables (works locally via .env and on GitHub
Actions via repo secrets):
  GMAIL_USER          sending Gmail address (e.g. stkotum@gmail.com)
  GMAIL_APP_PASSWORD  16-char Google App password (NOT the normal password)
  ALERT_TO            recipient (defaults to stephan.kohlhaas@tum.de)
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

from checker import RESERVE_URL  # single source of truth for the reservation URL

DEFAULT_RECIPIENT = "stephan.kohlhaas@tum.de"
FOOTER = (
    f"\nReserve a freed plate on the official portal (~2.60 €, holds it 90 days):\n"
    f"{RESERVE_URL}\n\n— your FS Wunschkennzeichen watcher"
)


def _config():
    user = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipient = os.environ.get("ALERT_TO", DEFAULT_RECIPIENT).strip()
    if not user or not password:
        raise RuntimeError(
            "GMAIL_USER and GMAIL_APP_PASSWORD must be set. "
            "Create an App password at https://myaccount.google.com/apppasswords"
        )
    return user, password, recipient


def _send(subject, body):
    user, password, recipient = _config()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = recipient
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(user, password)
        server.send_message(msg)
    print(f"[notify] sent to {recipient}: {subject}")


def _join(items):
    return ", ".join(items) if items else "—"


def send_report(snapshot):
    """snapshot: list of {label, mode, available:[plates], taken_single:[plates]|None}."""
    lines = ["Status report — FS Wunschkennzeichen watch (Freising)", ""]
    total_avail = 0
    for fam in snapshot:
        lines.append(f"== {fam['label']} ==")
        lines.append(f"Available now: {_join(fam['available'])}")
        total_avail += len(fam["available"])
        if fam.get("taken_single") is not None:
            lines.append(f"Still taken (watching these): {_join(fam['taken_single'])}")
        lines.append("")
    subject = f"🅿️ FS plate watch — status report ({total_avail} available now)"
    _send(subject, "\n".join(lines) + FOOTER)


def send_changes(changes):
    """changes: list of {label, new:[plates], gone:[plates]} (only families with changes)."""
    n_new = sum(len(c["new"]) for c in changes)
    n_gone = sum(len(c["gone"]) for c in changes)
    lines = ["Change detected in your FS plate watch:", ""]
    for c in changes:
        lines.append(f"== {c['label']} ==")
        if c["new"]:
            lines.append(f"🎉 NEWLY AVAILABLE: {_join(c['new'])}")
        if c["gone"]:
            lines.append(f"no longer available: {_join(c['gone'])}")
        lines.append("")
    subject = f"🎉 FS plate: {n_new} newly available" if n_new else f"FS plate: {n_gone} no longer available"
    _send(subject, "\n".join(lines) + FOOTER)


def send_test():
    _send("FS plate watch — test email ✔",
          "If you can read this, your Gmail credentials work and alerts will reach you." + FOOTER)


if __name__ == "__main__":
    send_test()
