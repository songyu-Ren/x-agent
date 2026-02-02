import logging
from app.agents.base import BaseAgent
from app.models import ApprovedDraftRecord, NotificationResult
from app.config import settings
from app.services.email_service import send_email_html
from app.services.whatsapp_service import send_whatsapp

logger = logging.getLogger(__name__)

class NotifierAgent(BaseAgent):
    def __init__(self):
        super().__init__("NotifierAgent")

    def run(self, record: ApprovedDraftRecord) -> NotificationResult:
        errors: list[str] = []
        email_ok = self._send_email(record, errors)
        wa_ok = False
        if settings.ENABLE_WHATSAPP:
            wa_ok = self._send_whatsapp(record, errors)
            
        return NotificationResult(email_sent=email_ok, whatsapp_sent=wa_ok, errors=errors)

    def _render_text(self, record: ApprovedDraftRecord) -> str:
        if record.mode == "thread" and record.tweets:
            return "\n\n".join(record.tweets)
        return record.text or ""

    def _send_email(self, record: ApprovedDraftRecord, errors: list[str]) -> bool:
        preview = (record.text or (record.tweets[0] if record.tweets else ""))
        subject = f"Daily X Draft: {record.policy_report.action} - {preview[:30]}..."
        
        base_url = settings.BASE_PUBLIC_URL.rstrip("/")
        approve_link = f"{base_url}/approve/{record.token}"
        edit_link = f"{base_url}/edit/{record.token}"
        skip_link = f"{base_url}/skip/{record.token}"
        
        rendered_text = self._render_text(record)
        html = f"""
        <h2>Daily X Draft ({record.policy_report.risk_level})</h2>
        <p><strong>Policy Action:</strong> {record.policy_report.action}</p>
        <div style="border: 1px solid #ccc; padding: 15px; background: #f9f9f9; margin: 10px 0;">
            <pre style="white-space: pre-wrap; font-size: 14px;">{rendered_text}</pre>
        </div>
        
        <h3>Policy Check:</h3>
        <ul>
        {''.join([f"<li>{c.check_name}: {'✅' if c.passed else '❌'} - {c.details}</li>" for c in record.policy_report.checks])}
        </ul>
        
        <div style="margin-top: 20px;">
            <a href="{approve_link}" style="background:green; color:white; padding:10px 20px; text-decoration:none; margin-right:10px;">Approve & Post</a>
            <a href="{edit_link}" style="background:blue; color:white; padding:10px 20px; text-decoration:none; margin-right:10px;">Edit</a>
            <a href="{skip_link}" style="background:gray; color:white; padding:10px 20px; text-decoration:none;">Skip</a>
        </div>
        """
        
        try:
            send_email_html(subject, html)
            return True
        except Exception as e:
            errors.append(f"email_failed:{str(e)[:200]}")
            logger.error("Email failed", exc_info=True)
            return False

    def _send_whatsapp(self, record: ApprovedDraftRecord, errors: list[str]) -> bool:
        try:
            base_url = settings.BASE_PUBLIC_URL.rstrip("/")
            body = f"Daily X Draft:\n\n{self._render_text(record)}\n\nApprove: {base_url}/approve/{record.token}\nEdit: {base_url}/edit/{record.token}\nSkip: {base_url}/skip/{record.token}"
            send_whatsapp(body)
            return True
        except Exception:
            errors.append("whatsapp_failed")
            return False
