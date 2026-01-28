"""
Review Alert System.

Composes review alert emails (single review + weekly digest) using
the existing ReviewResponseGenerator for AI responses and EmailService
for delivery.

Standalone usage:
    from src.services.review_alerts import ReviewAlertService, ReviewAlertInput, ReviewData

    service = ReviewAlertService()
    alert = ReviewAlertInput(
        business_name="Pawfect Grooming",
        business_email="owner@pawfect.com",
        business_type="dog grooming salon",
        google_place_id="ChIJ...",
        review=ReviewData(reviewer_name="Emma", rating=5.0,
                          review_text="Loved it!", review_date="2026-01-25"),
    )
    subject, html, plain = await service.render_review_alert(alert)
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field

from src.services.response_generator import (
    ReviewInput,
    ReviewResponse,
    ReviewResponseGenerator,
)

# =============================================================================
# Constants
# =============================================================================

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

GOOGLE_REVIEW_BASE = "https://search.google.com/local/writereview?placeid="

_STAR_FILLED = "&#9733;"   # ★
_STAR_EMPTY = "&#9734;"    # ☆


# =============================================================================
# Models
# =============================================================================


class ReviewData(BaseModel):
    """A single review."""
    reviewer_name: str
    rating: float = Field(..., ge=1.0, le=5.0)
    review_text: str
    review_date: str = Field(..., description="Display-friendly date string")
    platform: str = Field("Google", description="Review platform name")


class ReviewAlertInput(BaseModel):
    """Input for a single-review alert email."""
    business_name: str
    business_email: str
    business_type: str
    google_place_id: str
    review: ReviewData


class WeeklyDigestInput(BaseModel):
    """Input for a weekly digest email."""
    business_name: str
    business_email: str
    business_type: str
    google_place_id: str
    reviews: list[ReviewData]
    period_start: str = Field(..., description="e.g. '20 Jan 2026'")
    period_end: str = Field(..., description="e.g. '26 Jan 2026'")
    prev_avg_rating: Optional[float] = Field(
        None, description="Previous week's average rating for comparison"
    )


# =============================================================================
# Helpers
# =============================================================================


def format_star_rating(rating: float, mode: str = "html") -> str:
    """Return a star string for a numeric rating.

    Args:
        rating: Star rating (1-5).
        mode: 'html' for HTML entities, 'text' for unicode characters.

    Returns:
        Star string, e.g. '★★★★☆' for 4.0.
    """
    filled = round(rating)
    if mode == "html":
        return (_STAR_FILLED * filled) + (_STAR_EMPTY * (5 - filled))
    # plain-text / unicode
    return ("\u2605" * filled) + ("\u2606" * (5 - filled))


def _build_google_review_url(place_id: str) -> str:
    return f"{GOOGLE_REVIEW_BASE}{place_id}"


def _rating_colour(rating: float) -> str:
    """Return a CSS colour for a rating value."""
    if rating >= 4.0:
        return "#4caf50"
    if rating >= 3.0:
        return "#ff9800"
    return "#f44336"


# =============================================================================
# Service
# =============================================================================


class ReviewAlertService:
    """Composes and optionally sends review alert emails.

    Uses ReviewResponseGenerator for AI responses and Jinja2 templates
    for email rendering. Email delivery is delegated to EmailService.
    """

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=["html"]),
        )
        self._alert_tpl = self._env.get_template("review_alert_email.html")
        self._digest_tpl = self._env.get_template("weekly_digest_email.html")
        self._responder = ReviewResponseGenerator()

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    async def _generate_ai_response(
        self, review: ReviewData, business_name: str, business_type: str,
    ) -> ReviewResponse:
        """Generate an AI response for a single review."""
        review_input = ReviewInput(
            reviewer_name=review.reviewer_name,
            rating=review.rating,
            review_text=review.review_text,
            business_name=business_name,
            business_type=business_type,
        )
        return await self._responder.generate_response(review_input)

    # -----------------------------------------------------------------
    # Single review alert
    # -----------------------------------------------------------------

    async def render_review_alert(
        self, alert: ReviewAlertInput,
    ) -> tuple[str, str, str]:
        """Render a single-review alert email.

        Args:
            alert: Input data for the alert.

        Returns:
            Tuple of (subject, html_body, plain_text_body).
        """
        ai = await self._generate_ai_response(
            alert.review, alert.business_name, alert.business_type,
        )

        google_url = _build_google_review_url(alert.google_place_id)
        stars_html = format_star_rating(alert.review.rating, mode="html")

        context = {
            "business_name": alert.business_name,
            "reviewer_name": alert.review.reviewer_name,
            "rating": alert.review.rating,
            "stars_html": stars_html,
            "review_text": alert.review.review_text,
            "review_date": alert.review.review_date,
            "platform": alert.review.platform,
            "ai_response": ai.response_text,
            "ai_response_encoded": quote(ai.response_text, safe=""),
            "strategy": ai.strategy.value.replace("_", " ").title(),
            "google_review_url": google_url,
            "year": datetime.now().year,
        }

        html = self._alert_tpl.render(**context)
        subject = (
            f"{'⭐' * round(alert.review.rating)} New {alert.review.platform} "
            f"Review — {alert.review.reviewer_name}"
        )

        plain = (
            f"New {alert.review.rating}/5 review from {alert.review.reviewer_name} "
            f"on {alert.review.platform}\n\n"
            f"\"{alert.review.review_text}\"\n\n"
            f"Suggested response:\n{ai.response_text}\n\n"
            f"View on Google: {google_url}"
        )

        return subject, html, plain

    async def send_review_alert(self, alert: ReviewAlertInput) -> bool:
        """Render and send a single-review alert email.

        Args:
            alert: Input data for the alert.

        Returns:
            True if sent successfully, False otherwise.
        """
        from src.delivery.email_service import get_email_service

        subject, html, plain = await self.render_review_alert(alert)
        service = get_email_service()
        return await service._send_email(
            to_email=alert.business_email,
            subject=subject,
            html_content=html,
            plain_content=plain,
        )

    # -----------------------------------------------------------------
    # Weekly digest
    # -----------------------------------------------------------------

    async def render_weekly_digest(
        self, digest: WeeklyDigestInput,
    ) -> tuple[str, str, str]:
        """Render a weekly digest email.

        Args:
            digest: Input data for the digest.

        Returns:
            Tuple of (subject, html_body, plain_text_body).
        """
        # Generate AI responses for every review
        review_items = []
        for review in digest.reviews:
            ai = await self._generate_ai_response(
                review, digest.business_name, digest.business_type,
            )
            review_items.append({
                "reviewer_name": review.reviewer_name,
                "rating": review.rating,
                "stars_html": format_star_rating(review.rating, mode="html"),
                "review_text": review.review_text,
                "review_date": review.review_date,
                "ai_response": ai.response_text,
            })

        # Stats
        total_reviews = len(digest.reviews)
        ratings = [r.rating for r in digest.reviews]
        avg_rating = round(sum(ratings) / total_reviews, 1) if total_reviews else 0.0

        # Rating trend
        if digest.prev_avg_rating is not None:
            diff = round(avg_rating - digest.prev_avg_rating, 1)
            if diff > 0:
                trend_icon = "&#x25B2;"  # ▲
                trend_colour = "#4caf50"
                rating_diff = f"+{diff}"
            elif diff < 0:
                trend_icon = "&#x25BC;"  # ▼
                trend_colour = "#f44336"
                rating_diff = str(diff)
            else:
                trend_icon = "&#x2014;"  # —
                trend_colour = "#888"
                rating_diff = "0.0"
        else:
            trend_icon = "&#x2014;"
            trend_colour = "#888"
            rating_diff = "N/A"

        # Rating distribution
        counts = {s: 0 for s in range(1, 6)}
        for r in ratings:
            counts[round(r)] += 1
        distribution = {}
        for s in range(1, 6):
            distribution[s] = round((counts[s] / total_reviews) * 100) if total_reviews else 0

        # Simple insights
        insights = self._generate_insights(digest.reviews, avg_rating)

        google_url = _build_google_review_url(digest.google_place_id)

        context = {
            "business_name": digest.business_name,
            "period_start": digest.period_start,
            "period_end": digest.period_end,
            "total_reviews": total_reviews,
            "avg_rating": avg_rating,
            "trend_icon": trend_icon,
            "trend_colour": trend_colour,
            "rating_diff": rating_diff,
            "counts": counts,
            "distribution": distribution,
            "insights": insights,
            "review_items": review_items,
            "google_review_url": google_url,
            "year": datetime.now().year,
        }

        html = self._digest_tpl.render(**context)
        subject = (
            f"Weekly Digest: {total_reviews} reviews, "
            f"{avg_rating}/5 avg — {digest.business_name}"
        )

        # Plain text
        plain_reviews = []
        for item in review_items:
            stars_text = format_star_rating(item["rating"], mode="text")
            plain_reviews.append(
                f"{stars_text}  {item['reviewer_name']} ({item['review_date']})\n"
                f"\"{item['review_text']}\"\n"
                f"Suggested response: {item['ai_response']}"
            )

        plain = (
            f"Weekly Review Digest — {digest.business_name}\n"
            f"{digest.period_start} — {digest.period_end}\n\n"
            f"Total reviews: {total_reviews}\n"
            f"Average rating: {avg_rating}/5\n\n"
            + "\n\n".join(plain_reviews)
            + f"\n\nView all on Google: {google_url}"
        )

        return subject, html, plain

    async def send_weekly_digest(self, digest: WeeklyDigestInput) -> bool:
        """Render and send a weekly digest email.

        Args:
            digest: Input data for the digest.

        Returns:
            True if sent successfully, False otherwise.
        """
        from src.delivery.email_service import get_email_service

        subject, html, plain = await self.render_weekly_digest(digest)
        service = get_email_service()
        return await service._send_email(
            to_email=digest.business_email,
            subject=subject,
            html_content=html,
            plain_content=plain,
        )

    # -----------------------------------------------------------------
    # Insight generation (rule-based, no LLM)
    # -----------------------------------------------------------------

    @staticmethod
    def _generate_insights(reviews: list[ReviewData], avg_rating: float) -> list[str]:
        """Generate simple textual insights from the week's reviews."""
        if not reviews:
            return []

        insights = []
        total = len(reviews)

        # Positive/negative split
        positive = sum(1 for r in reviews if r.rating >= 4)
        negative = sum(1 for r in reviews if r.rating <= 2)
        if positive == total:
            insights.append(f"All {total} reviews were positive (4+ stars).")
        elif negative > 0:
            insights.append(
                f"{negative} of {total} review{'s' if negative != 1 else ''} "
                f"{'were' if negative != 1 else 'was'} negative (2 stars or below)."
            )

        # Keyword mentions
        keyword_groups = {
            "wait time": ["wait", "waiting", "slow", "delayed", "late"],
            "staff friendliness": ["friendly", "rude", "helpful", "staff", "welcoming"],
            "pricing": ["price", "expensive", "cheap", "value", "cost", "overpriced"],
            "cleanliness": ["clean", "dirty", "hygiene", "hygienic", "spotless"],
        }

        texts = " ".join(r.review_text.lower() for r in reviews)
        for topic, keywords in keyword_groups.items():
            matches = sum(1 for kw in keywords if kw in texts)
            if matches >= 2:
                mention_count = sum(
                    1 for r in reviews
                    if any(kw in r.review_text.lower() for kw in keywords)
                )
                if mention_count > 0:
                    insights.append(
                        f"{mention_count} review{'s' if mention_count != 1 else ''} "
                        f"mentioned {topic}."
                    )

        # Average rating note
        if avg_rating >= 4.5:
            insights.append(f"Excellent week — {avg_rating}/5 average rating.")
        elif avg_rating < 3.0:
            insights.append(
                f"Below-average week at {avg_rating}/5. "
                f"Consider reviewing the negative feedback for patterns."
            )

        return insights


# =============================================================================
# Singleton
# =============================================================================

_service_instance: Optional[ReviewAlertService] = None


def get_review_alert_service() -> ReviewAlertService:
    """Get or create the singleton ReviewAlertService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ReviewAlertService()
    return _service_instance


def reset_review_alert_service() -> None:
    """Reset the singleton (for testing)."""
    global _service_instance
    _service_instance = None
