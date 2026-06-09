"""Email out: a full status report, a change alert, or a credentials test.

Subjects/bodies are pure ASCII (emoji in the subject makes strict filters like TUM
quarantine the mail). Recipients are passed in explicitly by the caller (monitor.py),
so different audiences get different content.

Credentials from environment (local .env or GitHub Actions secrets):
  GMAIL_USER, GMAIL_APP_PASSWORD
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

FOOTER = (
    "\nReserve quickly on the district's official Wunschkennzeichen / i-Kfz portal "
    "(~2.60 EUR, holds it 90 days).\n\n-- your Wunschkennzeichen watcher"
)


def _auth():
    user = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    if not user or not password:
        raise RuntimeError("GMAIL_USER and GMAIL_APP_PASSWORD must be set "
                           "(App password: https://myaccount.google.com/apppasswords)")
    return user, password


def _send(subject, body, recipients):
    user, password = _auth()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(user, password)
        server.send_message(msg)
    print(f"[notify] sent to {recipients}: {subject}")


def _join(items):
    return ", ".join(items) if items else "(none)"


def send_report(snapshot, recipients):
    """snapshot: list of {label, available:[plates], taken_single:[plates]|None}."""
    lines = ["Status report - Wunschkennzeichen watch", ""]
    total = 0
    for fam in snapshot:
        lines.append(f"== {fam['label']} ==")
        lines.append(f"Available now: {_join(fam['available'])}")
        total += len(fam["available"])
        if fam.get("taken_single") is not None:
            lines.append(f"Still taken (watching these): {_join(fam['taken_single'])}")
        lines.append("")
    _send(f"Kennzeichen watch - status report ({total} available now)",
          "\n".join(lines) + FOOTER, recipients)


def send_changes(changes, recipients):
    """changes: list of {label, new:[plates], gone:[plates]} (only changed families)."""
    n_new = sum(len(c["new"]) for c in changes)
    n_gone = sum(len(c["gone"]) for c in changes)
    lines = ["Change detected in your plate watch:", ""]
    for c in changes:
        lines.append(f"== {c['label']} ==")
        if c["new"]:
            lines.append(f"NEWLY AVAILABLE: {_join(c['new'])}")
        if c["gone"]:
            lines.append(f"no longer available: {_join(c['gone'])}")
        lines.append("")
    subject = (f"ALERT: Kennzeichen - {n_new} newly available" if n_new
               else f"ALERT: Kennzeichen - {n_gone} no longer available")
    _send(subject, "\n".join(lines) + FOOTER, recipients)


def send_test(recipients):
    _send("Kennzeichen watch - test email",
          "If you can read this, the watcher's email credentials work." + FOOTER, recipients)


if __name__ == "__main__":
    send_test([os.environ.get("GMAIL_USER", "")])
