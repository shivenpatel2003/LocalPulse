"""
Output Generation and Delivery.

This module handles report generation and notification delivery:

- email_service: SendGrid-based email delivery
- templates/: Jinja2 email templates for various report types
- charts: Plotly-based visualization generation
- reports: Report builder combining insights, charts, and formatting

Delivery capabilities:
- Weekly insight digests via email
- Real-time alert notifications
- PDF report generation
- Interactive dashboard data

Example:
    from src.delivery import EmailService, get_email_service

    # Using singleton
    email_service = get_email_service()
    await email_service.send_report(
        to_email="owner@restaurant.com",
        business_name="My Restaurant",
        report_html="<html>...</html>",
        report_date="January 2024",
    )

    # Or instantiate directly
    service = EmailService()
    await service.send_welcome_email(
        to_email="owner@restaurant.com",
        business_name="My Restaurant",
    )
"""

from src.delivery.email_service import EmailService, get_email_service

__all__ = ["EmailService", "get_email_service"]
