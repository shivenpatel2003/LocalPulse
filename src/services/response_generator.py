"""
Review Response Generator.

Uses Claude to generate personalized, professional responses to customer
reviews. Adapts tone to business type and handles negative reviews with
empathy and resolution offers.

Standalone usage:
    from src.services.response_generator import ReviewResponseGenerator, ReviewInput
    generator = ReviewResponseGenerator()
    review = ReviewInput(
        reviewer_name="Sarah",
        rating=5.0,
        review_text="Amazing grooming for my poodle!",
        business_name="Pawfect Grooming",
        business_type="dog grooming salon",
    )
    response = await generator.generate_response(review)
"""

import json
import re
from enum import Enum
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from src.config.industry_schema import IndustryConfig
from src.config.settings import get_settings


# =============================================================================
# Models
# =============================================================================


class ResponseTone(str, Enum):
    """Tone presets for review responses."""
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    WARM = "warm"
    CASUAL = "casual"


class ResponseStrategy(str, Enum):
    """Strategy applied based on review sentiment."""
    GRATITUDE = "gratitude"
    EMPATHY_AND_RESOLUTION = "empathy_and_resolution"
    BALANCED_ACKNOWLEDGEMENT = "balanced_acknowledgement"


class ReviewInput(BaseModel):
    """Input data for generating a review response."""
    reviewer_name: str = Field(..., description="Name of the reviewer")
    rating: float = Field(..., ge=1.0, le=5.0, description="Star rating (1-5)")
    review_text: str = Field(..., description="Full text of the review")
    business_name: str = Field(..., description="Name of the business")
    business_type: str = Field(..., description="Type of business, e.g. 'dog grooming salon'")
    industry_config: Optional[IndustryConfig] = Field(
        None, description="Optional IndustryConfig for richer context"
    )


class ReviewResponse(BaseModel):
    """Generated response to a customer review."""
    response_text: str = Field(..., description="The generated response text")
    tone_used: ResponseTone = Field(..., description="Tone applied to the response")
    strategy: ResponseStrategy = Field(..., description="Strategy used for this response")
    word_count: int = Field(..., description="Word count of the response")


# =============================================================================
# Tone Mapping
# =============================================================================

# Maps business type keywords to appropriate tones
TONE_MAP: dict[str, ResponseTone] = {
    "grooming": ResponseTone.FRIENDLY,
    "pet": ResponseTone.FRIENDLY,
    "salon": ResponseTone.FRIENDLY,
    "cafe": ResponseTone.WARM,
    "restaurant": ResponseTone.WARM,
    "bakery": ResponseTone.WARM,
    "bar": ResponseTone.CASUAL,
    "pub": ResponseTone.CASUAL,
    "accountant": ResponseTone.PROFESSIONAL,
    "solicitor": ResponseTone.PROFESSIONAL,
    "lawyer": ResponseTone.PROFESSIONAL,
    "dentist": ResponseTone.PROFESSIONAL,
    "clinic": ResponseTone.PROFESSIONAL,
    "plumber": ResponseTone.FRIENDLY,
    "electrician": ResponseTone.FRIENDLY,
    "gym": ResponseTone.CASUAL,
    "fitness": ResponseTone.CASUAL,
}

DEFAULT_TONE = ResponseTone.PROFESSIONAL


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are a review response assistant for small businesses. Your job is to write
a short, personalized reply that the business owner can post in response to a customer review.

RULES:
- Write exactly 2-4 sentences. Never exceed 4 sentences.
- Use the reviewer's first name.
- Never use generic filler like "We appreciate all feedback" without specifics.
- Reference something specific from their review to show you read it.
- Do NOT include any greeting prefix like "Dear" or "Hi" at the very start — jump straight
  into the response with the reviewer's name woven naturally into the text.
- Do NOT include a sign-off like "Best regards" or the business name at the end.

TONE INSTRUCTIONS:
- friendly: Warm, enthusiastic, use exclamation marks sparingly. Think local shop owner.
- professional: Polished and courteous. Think solicitor or medical practice.
- warm: Genuine and caring. Think family restaurant or bakery.
- casual: Relaxed and personable. Think gym or pub.

STRATEGY BY RATING:
- 4-5 stars: GRATITUDE. Thank them genuinely. Reinforce what they loved. Invite them back.
- 3 stars: BALANCED. Acknowledge the positives they mentioned. Address any negatives with
  a concrete improvement or invitation to discuss further.
- 1-2 stars: EMPATHY_AND_RESOLUTION. Lead with empathy — acknowledge their frustration.
  Briefly apologise for the specific issue they raised. Offer to make it right by inviting
  them to contact you directly (email or phone). Never be defensive.

Return your response as JSON with this exact structure:
{
  "response_text": "The reply text",
  "tone_used": "friendly|professional|warm|casual",
  "strategy": "gratitude|empathy_and_resolution|balanced_acknowledgement"
}

Return ONLY the JSON object. No markdown, no explanation."""


# =============================================================================
# Generator
# =============================================================================


class ReviewResponseGenerator:
    """
    Generates personalised review responses using Claude.

    Follows the same Anthropic client pattern as ConfigGenerator.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        settings = get_settings()
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
        self.model = model

    def _resolve_tone(self, review: ReviewInput) -> ResponseTone:
        """Determine the appropriate tone for a business type."""
        # If an IndustryConfig is provided, map its report tone
        if review.industry_config and review.industry_config.report_config:
            tone_val = review.industry_config.report_config.tone.value
            try:
                return ResponseTone(tone_val)
            except ValueError:
                pass  # Fall through to keyword matching

        # Keyword matching on business_type
        bt_lower = review.business_type.lower()
        for keyword, tone in TONE_MAP.items():
            if keyword in bt_lower:
                return tone

        return DEFAULT_TONE

    def _determine_strategy(self, rating: float) -> ResponseStrategy:
        """Pick a response strategy based on the star rating."""
        if rating >= 4.0:
            return ResponseStrategy.GRATITUDE
        if rating >= 3.0:
            return ResponseStrategy.BALANCED_ACKNOWLEDGEMENT
        return ResponseStrategy.EMPATHY_AND_RESOLUTION

    def _build_user_message(self, review: ReviewInput, tone: ResponseTone,
                            strategy: ResponseStrategy) -> str:
        """Construct the user message sent to Claude."""
        parts = [
            f"Business: {review.business_name} ({review.business_type})",
            f"Reviewer: {review.reviewer_name}",
            f"Rating: {review.rating}/5",
            f"Review: {review.review_text}",
            f"Tone: {tone.value}",
            f"Strategy: {strategy.value}",
        ]

        if review.industry_config:
            theme_names = [t.display_name for t in review.industry_config.themes[:5]]
            if theme_names:
                parts.append(f"Business focus areas: {', '.join(theme_names)}")

        return "\n".join(parts)

    def _parse_response(self, text: str) -> dict:
        """Parse JSON from Claude's response."""
        text = text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse JSON from response: {text[:500]}")

    async def generate_response(self, review: ReviewInput) -> ReviewResponse:
        """
        Generate a review response for the given review.

        Args:
            review: The review input containing text, rating, and business context.

        Returns:
            A ReviewResponse with the generated text, tone, strategy, and word count.
        """
        tone = self._resolve_tone(review)
        strategy = self._determine_strategy(review.rating)
        user_message = self._build_user_message(review, tone, strategy)

        raw = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        result = self._parse_response(raw.content[0].text)

        response_text = result["response_text"]
        return ReviewResponse(
            response_text=response_text,
            tone_used=ResponseTone(result.get("tone_used", tone.value)),
            strategy=ResponseStrategy(result.get("strategy", strategy.value)),
            word_count=len(response_text.split()),
        )


# =============================================================================
# Singleton
# =============================================================================

_generator_instance: Optional[ReviewResponseGenerator] = None


def get_response_generator() -> ReviewResponseGenerator:
    """Get or create the singleton ReviewResponseGenerator."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ReviewResponseGenerator()
    return _generator_instance


def reset_response_generator() -> None:
    """Reset the singleton (for testing)."""
    global _generator_instance
    _generator_instance = None
