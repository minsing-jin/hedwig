from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
import unicodedata

from hedwig.config import SMTP_FROM, SMTP_HOST, SMTP_PASS, SMTP_PORT, SMTP_USER
from hedwig.models import ScoredSignal

logger = logging.getLogger(__name__)


def _smtp_port() -> int:
    try:
        return int(SMTP_PORT)
    except (TypeError, ValueError):
        return 587


def _default_recipient() -> str:
    if SMTP_USER and "@" in SMTP_USER:
        return SMTP_USER
    return SMTP_FROM


def _sanitize_header_value(value: str) -> str:
    cleaned = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in (value or "")
    )
    return " ".join(cleaned.split())


def _format_address(value: str) -> str:
    sanitized = _sanitize_header_value(value)
    display_name, address = parseaddr(sanitized)
    if not address:
        return sanitized
    return formataddr(
        (
            _sanitize_header_value(display_name),
            _sanitize_header_value(address),
        )
    )


def _build_alert_message(signal: ScoredSignal, recipient: str) -> EmailMessage:
    message = EmailMessage()
    subject = _sanitize_header_value(signal.raw.title)[:120] or "Untitled signal"
    message["Subject"] = f"[Hedwig Alert] {subject}"
    message["From"] = _format_address(SMTP_FROM)
    message["To"] = _format_address(recipient)
    message.set_content(
        "\n".join(
            [
                f"Title: {signal.raw.title}",
                f"Source: {signal.raw.platform.value}",
                f"URL: {signal.raw.url}",
                f"Relevance: {signal.relevance_score:.2f}",
                f"Urgency: {signal.urgency.value}",
                "",
                signal.raw.content,
                "",
                f"Why it matters: {signal.why_relevant or '—'}",
                f"Devil's advocate: {signal.devils_advocate or '—'}",
            ]
        )
    )
    return message


def _build_briefing_message(briefing_text: str, recipient: str, briefing_type: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"[Hedwig {briefing_type}] Briefing"
    message["From"] = _format_address(SMTP_FROM)
    message["To"] = _format_address(recipient)
    message.set_content(briefing_text)
    return message


def _send_message(message: EmailMessage) -> bool:
    with smtplib.SMTP(SMTP_HOST, _smtp_port(), timeout=10) as client:
        client.ehlo()
        if SMTP_USER and SMTP_PASS:
            if not client.has_extn("starttls"):
                raise RuntimeError("Authenticated SMTP requires STARTTLS support")
            client.starttls()
            client.ehlo()
            client.login(SMTP_USER, SMTP_PASS)
        client.send_message(message)
    return True


async def send_alert(signal: ScoredSignal, to_email: str | None = None) -> bool:
    """Send an alert-level signal via SMTP email."""
    recipient = to_email or _default_recipient()
    if not SMTP_HOST or not SMTP_FROM or not recipient:
        return False

    try:
        message = _build_alert_message(signal, recipient=recipient)
        return await asyncio.to_thread(_send_message, message)
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


async def _send_briefing(briefing_text: str, briefing_type: str, to_email: str | None = None) -> bool:
    recipient = to_email or _default_recipient()
    if not SMTP_HOST or not SMTP_FROM or not recipient:
        return False

    try:
        message = _build_briefing_message(briefing_text, recipient=recipient, briefing_type=briefing_type)
        return await asyncio.to_thread(_send_message, message)
    except Exception as e:
        logger.error(f"Failed to send email {briefing_type.lower()} briefing: {e}")
        return False


async def send_daily_briefing(briefing_text: str, to_email: str | None = None) -> bool:
    """Send the daily briefing via SMTP email."""
    return await _send_briefing(briefing_text, "Daily", to_email=to_email)


async def send_weekly_briefing(briefing_text: str, to_email: str | None = None) -> bool:
    """Send the weekly briefing via SMTP email."""
    return await _send_briefing(briefing_text, "Weekly", to_email=to_email)
