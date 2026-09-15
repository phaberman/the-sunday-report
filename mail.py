"""SMTP send of the week spreadsheet. Gmail: app password, not account password."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from db import ROOT
from odds import load_dotenv


def parse_recipients(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def send_xlsx(
    *,
    to: list[str],
    subject: str,
    body: str,
    filename: str,
    data: bytes,
) -> int:
    load_dotenv(ROOT / ".env")
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    from_addr = (
        os.environ.get("EMAIL_FROM", "")
        or os.environ.get("SMTP_FROM", "")
        or user
    ).strip()
    if not to:
        raise RuntimeError("EMAIL_TO is empty")
    if not user or not password:
        raise RuntimeError("Missing SMTP_USER or SMTP_PASSWORD")
    if not from_addr:
        raise RuntimeError("Missing EMAIL_FROM / SMTP_USER")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    msg.set_content(body)
    msg.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return len(to)


def recipients_from_env() -> list[str]:
    load_dotenv(ROOT / ".env")
    return parse_recipients(os.environ.get("EMAIL_TO", ""))
