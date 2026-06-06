"""Transactional email via SMTP (console fallback in dev)."""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(*, to: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    settings = get_settings()
    if not smtp_configured():
        logger.warning(
            "SMTP not configured — email to %s not sent. Subject: %s\n%s",
            to,
            subject,
            text_body,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    logger.info("Sent email to %s: %s", to, subject)


def send_auth_link(*, to: str, subject: str, action: str, link: str) -> None:
    text = (
        f"{action} for MatchForge.\n\n"
        f"Open this link (expires soon):\n{link}\n\n"
        "If you did not request this, you can ignore this email."
    )
    html = (
        f"<p>{action} for <strong>MatchForge</strong>.</p>"
        f'<p><a href="{link}">Continue to MatchForge</a></p>'
        f'<p style="color:#666;font-size:14px">Or copy this link:<br>{link}</p>'
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    send_email(to=to, subject=subject, text_body=text, html_body=html)