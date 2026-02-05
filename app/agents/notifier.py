import logging

import requests
from jinja2 import Template

from app.agents.base import BaseAgent
from app.config import settings
from app.models import ApprovedDraftRecord, NotificationResult
from app.services.email_service import send_email_html
from app.services.whatsapp_service import send_whatsapp

logger = logging.getLogger(__name__)


class NotifierAgent(BaseAgent):
    def __init__(self):
        super().__init__("NotifierAgent")

    def run(self, record: ApprovedDraftRecord) -> NotificationResult:
        errors: list[str] = []
        email_ok = self._send_email(record, errors)
        try:
            from app.observability.metrics import NOTIFY_TOTAL

            NOTIFY_TOTAL.labels(channel="email", status=("success" if email_ok else "failed")).inc()
        except Exception:
            pass
        slack_ok = False
        if bool(getattr(settings, "ENABLE_SLACK", False)) and getattr(
            settings, "SLACK_WEBHOOK_URL", None
        ):
            slack_ok = self._send_slack(record, errors)
            try:
                from app.observability.metrics import NOTIFY_TOTAL

                NOTIFY_TOTAL.labels(
                    channel="slack", status=("success" if slack_ok else "failed")
                ).inc()
            except Exception:
                pass
        wa_ok = False
        if settings.ENABLE_WHATSAPP:
            wa_ok = self._send_whatsapp(record, errors)
            try:
                from app.observability.metrics import NOTIFY_TOTAL

                NOTIFY_TOTAL.labels(
                    channel="whatsapp", status=("success" if wa_ok else "failed")
                ).inc()
            except Exception:
                pass

        return NotificationResult(email_sent=email_ok, whatsapp_sent=wa_ok, errors=errors)

    def _render_text(self, record: ApprovedDraftRecord) -> str:
        if record.mode == "thread" and record.tweets:
            return "\n\n".join(record.tweets)
        return record.text or ""

    def _send_email(self, record: ApprovedDraftRecord, errors: list[str]) -> bool:
        preview = record.text or (record.tweets[0] if record.tweets else "")
        subject = f"Daily X Draft: {record.policy_report.action} - {preview[:30]}..."

        base_url = settings.BASE_PUBLIC_URL.rstrip("/")
        approve_link = f"{base_url}/approve/{record.approve_token}"
        edit_link = f"{base_url}/edit/{record.edit_token}"
        skip_link = f"{base_url}/skip/{record.skip_token}"

        rendered_text = self._render_text(record)
        template = Template(
            """
<h2>Daily X Draft ({{ risk_level }})</h2>
<p><strong>Policy Action:</strong> {{ action }}</p>
<div style="border: 1px solid #ccc; padding: 15px; background: #f9f9f9; margin: 10px 0;">
  <pre style="white-space: pre-wrap; font-size: 14px;">{{ rendered_text }}</pre>
</div>

<h3>Policy Check:</h3>
<ul>
{% for c in checks %}
  <li>{{ c.check_name }}: {{ "PASS" if c.passed else "FAIL" }} - {{ c.details }}</li>
{% endfor %}
</ul>

<div style="margin-top: 20px;">
  <a href="{{ approve_link }}" style="background:green; color:white; padding:10px 20px; text-decoration:none; margin-right:10px;">Approve &amp; Post</a>
  <a href="{{ edit_link }}" style="background:blue; color:white; padding:10px 20px; text-decoration:none; margin-right:10px;">Edit</a>
  <a href="{{ skip_link }}" style="background:gray; color:white; padding:10px 20px; text-decoration:none;">Skip</a>
</div>
"""
        )
        html = template.render(
            risk_level=str(record.policy_report.risk_level),
            action=str(record.policy_report.action),
            rendered_text=rendered_text,
            checks=list(record.policy_report.checks),
            approve_link=approve_link,
            edit_link=edit_link,
            skip_link=skip_link,
        )

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
            text = self._render_text(record).strip().replace("\n\n", "\n")
            snippet = (text[:240] + "…") if len(text) > 240 else text
            body = (
                f"Draft ({record.policy_report.action}/{record.policy_report.risk_level}):\n"
                f"{snippet}\n\n"
                f"Approve: {base_url}/approve/{record.approve_token}\n"
                f"Edit: {base_url}/edit/{record.edit_token}\n"
                f"Skip: {base_url}/skip/{record.skip_token}"
            )
            send_whatsapp(body)
            return True
        except Exception:
            errors.append("whatsapp_failed")
            return False

    def _send_slack(self, record: ApprovedDraftRecord, errors: list[str]) -> bool:
        try:
            webhook = str(getattr(settings, "SLACK_WEBHOOK_URL", "") or "")
            if not webhook:
                return False

            base_url = settings.BASE_PUBLIC_URL.rstrip("/")
            approve_link = f"{base_url}/approve/{record.approve_token}"
            edit_link = f"{base_url}/edit/{record.edit_token}"
            skip_link = f"{base_url}/skip/{record.skip_token}"

            text = self._render_text(record).strip().replace("\n\n", "\n")
            snippet = (text[:800] + "…") if len(text) > 800 else text
            payload = {
                "text": (
                    f"*Daily X Draft* ({record.policy_report.action}/{record.policy_report.risk_level})\n"
                    f"{snippet}\n\n"
                    f"<{approve_link}|Approve> • <{edit_link}|Edit> • <{skip_link}|Skip>"
                )
            }
            resp = requests.post(webhook, json=payload, timeout=10)
            if resp.status_code >= 400:
                errors.append(f"slack_failed:{resp.status_code}")
                return False
            return True
        except Exception as e:
            errors.append(f"slack_failed:{str(e)[:200]}")
            return False
