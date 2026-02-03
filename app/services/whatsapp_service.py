from twilio.rest import Client as TwilioClient

from app.config import settings
from app.services.retry import with_retry


def send_whatsapp(body: str) -> None:
    if not settings.ENABLE_WHATSAPP:
        return
    with_retry(lambda: _send(body), max_attempts=3)


def _send(body: str) -> None:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise RuntimeError("Twilio credentials missing")
    client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(
        from_=settings.TWILIO_FROM_NUMBER,
        to=settings.TWILIO_TO_NUMBER,
        body=body,
    )
