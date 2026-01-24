import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client as TwilioClient

from app.config import settings

logger = logging.getLogger(__name__)

def send_email(subject: str, html_content: str):
    """Send email via configured provider."""
    if settings.EMAIL_PROVIDER == "sendgrid":
        _send_sendgrid(subject, html_content)
    else:
        _send_smtp(subject, html_content)

def _send_sendgrid(subject: str, html_content: str):
    try:
        if not settings.SENDGRID_API_KEY:
            logger.error("SendGrid API Key not configured.")
            return

        message = Mail(
            from_email=settings.EMAIL_FROM,
            to_emails=settings.EMAIL_TO,
            subject=subject,
            html_content=html_content
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        logger.info(f"SendGrid email sent. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"SendGrid error: {e}")

def _send_smtp(subject: str, html_content: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = settings.EMAIL_TO

        part = MIMEText(html_content, "html")
        msg.attach(part)

        # Connect to SMTP
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        
        server.sendmail(settings.EMAIL_FROM, settings.EMAIL_TO, msg.as_string())
        server.quit()
        logger.info("SMTP email sent.")
    except Exception as e:
        logger.error(f"SMTP error: {e}")

def send_whatsapp(body: str):
    """Send WhatsApp message if enabled."""
    if not settings.ENABLE_WHATSAPP:
        return

    try:
        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_FROM_NUMBER,
            to=settings.TWILIO_TO_NUMBER,
            body=body
        )
        logger.info(f"WhatsApp message sent: {message.sid}")
    except Exception as e:
        logger.error(f"Twilio error: {e}")

def notify_user(token: str, final_text: str, is_attention_needed: bool = False):
    """Construct notification and send."""
    base_url = settings.BASE_PUBLIC_URL.rstrip("/")
    approve_link = f"{base_url}/approve/{token}"
    edit_link = f"{base_url}/edit/{token}"
    skip_link = f"{base_url}/skip/{token}"

    subject = f"Daily X Draft: {final_text[:30]}..."
    if is_attention_needed:
        subject = f"[ATTENTION] {subject}"

    html_body = f"""
    <h2>Daily X Draft</h2>
    <p><strong>Status:</strong> {'Needs Attention' if is_attention_needed else 'Ready'}</p>
    <div style="border: 1px solid #ccc; padding: 10px; margin: 10px 0; background: #f9f9f9;">
        <pre style="white-space: pre-wrap;">{final_text}</pre>
    </div>
    
    <p>
        <a href="{approve_link}" style="background:green; color:white; padding:10px; text-decoration:none; margin-right:10px;">Approve & Post</a>
        <a href="{edit_link}" style="background:blue; color:white; padding:10px; text-decoration:none; margin-right:10px;">Edit</a>
        <a href="{skip_link}" style="background:gray; color:white; padding:10px; text-decoration:none;">Skip</a>
    </p>
    """

    send_email(subject, html_body)

    if settings.ENABLE_WHATSAPP:
        wa_body = f"Daily X Draft:\n\n{final_text}\n\nApprove: {approve_link}\nEdit: {edit_link}\nSkip: {skip_link}"
        send_whatsapp(wa_body)
