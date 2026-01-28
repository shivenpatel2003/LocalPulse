"""
Review Request System.

Generates personalised review request messages (email and SMS) that
businesses can send to customers after a visit. Supports tone matching
by business type and constructs direct Google review links.

Standalone usage:
    from src.services.review_requests import ReviewRequestGenerator, ReviewRequestInput

    generator = ReviewRequestGenerator()
    req = ReviewRequestInput(
        customer_name="Sarah",
        business_name="Pawfect Grooming",
        business_type="dog grooming salon",
        google_place_id="ChIJ...",
    )
    email = generator.generate_email_request(req)
    sms   = generator.generate_sms_request(req)
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field


# =============================================================================
# Constants
# =============================================================================

GOOGLE_REVIEW_BASE = "https://search.google.com/local/writereview?placeid="

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

SMS_MAX_LENGTH = 160


# =============================================================================
# Models
# =============================================================================


class RequestChannel(str, Enum):
    """Delivery channel for a review request."""
    EMAIL = "email"
    SMS = "sms"


class ReviewRequestInput(BaseModel):
    """Input data for generating a review request."""
    customer_name: str = Field(..., description="Customer's first name")
    business_name: str = Field(..., description="Name of the business")
    business_type: str = Field(..., description="Type of business, e.g. 'dog grooming salon'")
    google_place_id: str = Field(..., description="Google Places ID for the review link")
    customer_email: Optional[str] = Field(None, description="Customer email address")
    customer_phone: Optional[str] = Field(None, description="Customer phone number")


class ReviewRequestRecord(BaseModel):
    """Tracks a review request that was sent (for future database storage)."""
    id: UUID = Field(default_factory=uuid4)
    customer_name: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    business_id: str = Field(..., description="Internal business identifier")
    channel: RequestChannel
    review_url: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    clicked_at: Optional[datetime] = Field(None, description="When the customer clicked the link")


class GeneratedRequest(BaseModel):
    """A generated review request message."""
    subject: Optional[str] = Field(None, description="Email subject line (None for SMS)")
    body: str = Field(..., description="Message body (HTML for email, plain text for SMS)")
    channel: RequestChannel
    review_url: str


# =============================================================================
# Helpers
# =============================================================================


def build_google_review_url(place_id: str) -> str:
    """Construct a direct Google review URL from a Google Place ID.

    Args:
        place_id: The Google Places identifier (e.g. 'ChIJN1t_tDeuEmsRUsoyG83frY4').

    Returns:
        Full URL that opens the Google review form for the business.
    """
    return f"{GOOGLE_REVIEW_BASE}{place_id}"


# =============================================================================
# Tone Copy
# =============================================================================

# Each tone provides copy fragments used by both templates.
# Keys: greeting, opening_line, ask_line, closing_line, sign_off, header_colour

_TONE_COPY = {
    "friendly": {
        "greeting": "Hi",
        "opening_line": "We hope you and your furry friend had a great experience with us!",
        "ask_line": "We'd really appreciate it if you could leave us a quick review — it helps other pet parents find us.",
        "closing_line": "Thanks so much — it means the world to us!",
        "sign_off": "Wagging tails,",
        "header_colour": "#4CAF50",
    },
    "warm": {
        "greeting": "Hello",
        "opening_line": "Thank you for choosing us — we hope you enjoyed your visit!",
        "ask_line": "If you have a moment, we'd love to hear how your experience was.",
        "closing_line": "Your feedback genuinely helps us improve and lets others know what to expect.",
        "sign_off": "With thanks,",
        "header_colour": "#E67E22",
    },
    "professional": {
        "greeting": "Dear",
        "opening_line": "Thank you for your recent visit. We trust everything met your expectations.",
        "ask_line": "We would be grateful if you could take a moment to share your experience.",
        "closing_line": "Your feedback is invaluable in helping us maintain the highest standards.",
        "sign_off": "Kind regards,",
        "header_colour": "#2C3E50",
    },
    "casual": {
        "greeting": "Hey",
        "opening_line": "Great to see you recently — hope you had a good time!",
        "ask_line": "Fancy leaving us a quick review? It really helps us out.",
        "closing_line": "Cheers — we appreciate it!",
        "sign_off": "See you soon,",
        "header_colour": "#3498DB",
    },
}

# Maps business-type keywords to tone keys (same logic as response_generator)
_TONE_MAP: dict[str, str] = {
    "grooming": "friendly",
    "pet": "friendly",
    "salon": "friendly",
    "cafe": "warm",
    "restaurant": "warm",
    "bakery": "warm",
    "bar": "casual",
    "pub": "casual",
    "accountant": "professional",
    "solicitor": "professional",
    "lawyer": "professional",
    "dentist": "professional",
    "clinic": "professional",
    "plumber": "friendly",
    "electrician": "friendly",
    "gym": "casual",
    "fitness": "casual",
}

_DEFAULT_TONE = "professional"


def _resolve_tone(business_type: str) -> str:
    """Pick a tone key based on the business type string."""
    bt_lower = business_type.lower()
    for keyword, tone in _TONE_MAP.items():
        if keyword in bt_lower:
            return tone
    return _DEFAULT_TONE


# =============================================================================
# Generator
# =============================================================================


class ReviewRequestGenerator:
    """
    Generates review request messages using Jinja2 templates.

    No LLM calls — review requests are formulaic and template-based.
    """

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=["html"]),
        )
        self._email_tpl = self._env.get_template("review_request_email.html")
        self._sms_tpl = self._env.get_template("review_request_sms.txt")

    def generate_email_request(self, req: ReviewRequestInput) -> GeneratedRequest:
        """Generate an HTML email review request.

        Args:
            req: Input containing customer name, business info, and place ID.

        Returns:
            A GeneratedRequest with HTML body, subject, and review URL.
        """
        review_url = build_google_review_url(req.google_place_id)
        tone = _resolve_tone(req.business_type)
        copy = _TONE_COPY[tone]

        # For non-pet businesses, swap in a generic opening line
        opening = copy["opening_line"]
        if "furry friend" in opening and "pet" not in req.business_type.lower() and "groom" not in req.business_type.lower():
            opening = "Thank you for your recent visit — we hope you had a wonderful experience!"

        context = {
            "customer_name": req.customer_name,
            "business_name": req.business_name,
            "review_url": review_url,
            "greeting": copy["greeting"],
            "opening_line": opening,
            "ask_line": copy["ask_line"],
            "closing_line": copy["closing_line"],
            "sign_off": copy["sign_off"],
            "header_colour": copy["header_colour"],
        }

        body = self._email_tpl.render(**context)
        subject = f"{req.business_name} — We'd Love Your Feedback!"

        return GeneratedRequest(
            subject=subject,
            body=body,
            channel=RequestChannel.EMAIL,
            review_url=review_url,
        )

    def generate_sms_request(self, req: ReviewRequestInput) -> GeneratedRequest:
        """Generate a short SMS review request (target: under 160 chars).

        Args:
            req: Input containing customer name, business info, and place ID.

        Returns:
            A GeneratedRequest with plain-text body and review URL.
        """
        review_url = build_google_review_url(req.google_place_id)
        tone = _resolve_tone(req.business_type)
        copy = _TONE_COPY[tone]

        # SMS needs a shorter ask line
        sms_ask = "We'd love a quick review:"

        context = {
            "customer_name": req.customer_name,
            "business_name": req.business_name,
            "review_url": review_url,
            "greeting": copy["greeting"],
            "ask_line": sms_ask,
        }

        body = self._sms_tpl.render(**context).strip()

        # If over 160 chars, shorten greeting
        if len(body) > SMS_MAX_LENGTH:
            context["greeting"] = "Hi"
            body = self._sms_tpl.render(**context).strip()

        return GeneratedRequest(
            subject=None,
            body=body,
            channel=RequestChannel.SMS,
            review_url=review_url,
        )


# =============================================================================
# Singleton
# =============================================================================

_generator_instance: Optional[ReviewRequestGenerator] = None


def get_request_generator() -> ReviewRequestGenerator:
    """Get or create the singleton ReviewRequestGenerator."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ReviewRequestGenerator()
    return _generator_instance


def reset_request_generator() -> None:
    """Reset the singleton (for testing)."""
    global _generator_instance
    _generator_instance = None
