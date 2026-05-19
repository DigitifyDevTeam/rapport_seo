"""Optional email delivery for finished reports."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from src.config import env

logger = logging.getLogger(__name__)


def send_report(recipients: list[str], subject: str, body: str,
                  attachment: Path) -> bool:
    if not recipients:
        return False
    host = env("SMTP_HOST")
    if not host:
        logger.info("SMTP_HOST not configured, skipping delivery")
        return False
    port = int(env("SMTP_PORT", "587") or 587)
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    sender = env("SMTP_FROM", username or "reports@example.com")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    if attachment and attachment.exists():
        message.add_attachment(attachment.read_bytes(),
                                 maintype="application",
                                 subtype="octet-stream",
                                 filename=attachment.name)

    try:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send report email: %s", exc)
        return False
    return True
