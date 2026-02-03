import logging
import smtplib
from contextlib import suppress
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config import settings
from app.services.retry import with_retry

logger = logging.getLogger(__name__)


def send_email_html(subject: str, html: str) -> None:
    provider = settings.EMAIL_PROVIDER
    if provider == "sendgrid":
        with_retry(lambda: _send_sendgrid(subject, html), max_attempts=3)
        return
    with_retry(lambda: _send_smtp(subject, html), max_attempts=3)


def _send_sendgrid(subject: str, html: str) -> None:
    if not settings.SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY missing")
    message = Mail(
        from_email=settings.EMAIL_FROM,
        to_emails=settings.EMAIL_TO,
        subject=subject,
        html_content=html,
    )
    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    sg.send(message)


def _send_smtp(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = settings.EMAIL_TO
    msg.attach(MIMEText(html, "html"))
    server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=20)
    try:
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, settings.EMAIL_TO, msg.as_string())
    finally:
        with suppress(Exception):
            server.quit()
