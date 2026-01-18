"""Unified schema for all collected content.

Provides ContentType enum and CollectedContent Pydantic model for
normalizing data from various sources to a common format.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContentType(Enum):
    """Types of collected content."""

    POST = "post"
    PROFILE = "profile"
    REVIEW = "review"
    ARTICLE = "article"
    COMMENT = "comment"
    BUSINESS = "business"


class CollectedContent(BaseModel):
    """Unified schema for all collected content.

    Provides a common structure for data from Twitter, Instagram,
    web scraping, and custom APIs.
    """

    # Identification
    id: str = Field(..., description="Unique ID within source")
    source: str = Field(..., description="Source identifier (twitter, instagram, web, etc.)")
    source_url: str | None = Field(None, description="Original URL")
    content_type: ContentType

    # Core content
    title: str | None = None
    text: str | None = None
    media_urls: list[str] = Field(default_factory=list)

    # Engagement (optional, for social media)
    likes: int | None = None
    shares: int | None = None
    comments_count: int | None = None
    views: int | None = None

    # Author/entity info
    author_id: str | None = None
    author_name: str | None = None
    author_handle: str | None = None

    # Timestamps
    created_at: datetime | None = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    # Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_data: dict[str, Any] | None = Field(
        None, description="Original response for debugging"
    )

    model_config = {"extra": "forbid"}
