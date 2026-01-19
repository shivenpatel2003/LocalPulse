"""Communication Agent tools for message delivery."""

import json
from langchain_core.tools import tool


@tool
async def send_email(
    to: str,
    subject: str,
    body: str,
    html: bool = False,
) -> str:
    """Send an email with the report.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body content
        html: Whether body is HTML formatted

    Returns:
        JSON string with send status.
    """
    try:
        from src.delivery.email_service import send_report_email

        # Attempt to send via email service
        result = await send_report_email(
            to_email=to,
            subject=subject,
            body=body,
            html=html,
        )
        return json.dumps({
            "status": "sent" if result else "failed",
            "to": to,
            "subject": subject,
        })

    except ImportError:
        # Email service not available
        return json.dumps({
            "status": "skipped",
            "reason": "Email service not configured",
            "to": to,
            "subject": subject,
        })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": str(e),
            "to": to,
        })
