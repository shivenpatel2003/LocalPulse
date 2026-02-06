"""Resend email service for LocalPulse."""
import httpx
import structlog
from typing import Optional
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

class EmailService:
    def __init__(self):
        settings = get_settings()
        self._api_key = settings.resend_api_key.get_secret_value() if settings.resend_api_key else None
        self._from_email = "reports@localpulse.io"
    
    @property
    def is_configured(self) -> bool:
        return self._api_key is not None
    
    async def _send_email(self, to_email: str, subject: str, html_content: str, **kwargs) -> bool:
        if not self._api_key:
            logger.warning("email_not_configured")
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "from": f"LocalPulse <{self._from_email}>",
                        "to": [to_email],
                        "subject": subject,
                        "html": html_content,
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    logger.info("email_sent", to=to_email)
                    return True
                logger.error("email_failed", status=resp.status_code, body=resp.text[:200])
                return False
        except Exception as e:
            logger.error("email_error", error=str(e))
            return False

    async def send_report(self, to_email: str, business_name: str, html_content: str, **kwargs) -> bool:
        subject = f"Your LocalPulse Report: {business_name}"
        return await self._send_email(to_email, subject, html_content)

    async def send_welcome_email(self, to_email: str, business_name: str, **kwargs) -> bool:
        subject = f"Welcome to LocalPulse, {business_name}!"
        html = f"<h1>Welcome!</h1><p>Your reports for {business_name} are now active.</p>"
        return await self._send_email(to_email, subject, html)

    async def send_alert(self, to_email: str, subject: str, html_content: str, **kwargs) -> bool:
        return await self._send_email(to_email, subject, html_content)

def get_email_service() -> EmailService:
    return EmailService()
