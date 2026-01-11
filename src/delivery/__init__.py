"""
Output Generation and Delivery.

This module handles report generation and notification delivery:

- templates/: Jinja2 email templates for various report types
- charts: Plotly-based visualization generation
- reports: Report builder combining insights, charts, and formatting

Delivery capabilities:
- Weekly insight digests via email
- Real-time alert notifications
- PDF report generation
- Interactive dashboard data

Example:
    from src.delivery import ReportBuilder, ChartGenerator

    charts = ChartGenerator()
    sentiment_chart = await charts.create_sentiment_trend(review_data)

    builder = ReportBuilder()
    report = await builder.build_weekly_digest(
        business_id="123",
        insights=insights,
        charts=[sentiment_chart]
    )
    await builder.send_email(report, recipient="owner@restaurant.com")
"""
