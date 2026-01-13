"""Pydantic models for LocalPulse core entities."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """Review platform sources."""
    GOOGLE = "google"
    TRIPADVISOR = "tripadvisor"
    FACEBOOK = "facebook"


class PriceRange(str, Enum):
    """Restaurant price range indicators."""
    BUDGET = "$"
    MODERATE = "$$"
    UPSCALE = "$$$"
    FINE_DINING = "$$$$"


# =============================================================================
# Base Models
# =============================================================================


class BaseEntity(BaseModel):
    """Base model with common fields and conversion methods."""

    class Config:
        from_attributes = True
        populate_by_name = True

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert model to Neo4j node properties.

        Neo4j doesn't support UUID or datetime directly, so we convert them.
        """
        data = self.model_dump()
        result = {}
        for key, value in data.items():
            if isinstance(value, UUID):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, (list, dict)):
                # Neo4j supports lists of primitives, but nested structures
                # should be serialized as JSON strings
                import json
                result[key] = json.dumps(value) if isinstance(value, dict) else value
            elif value is not None:
                result[key] = value
        return result

    @classmethod
    def from_neo4j_node(cls, node: dict[str, Any]) -> "BaseEntity":
        """Create model instance from Neo4j node properties."""
        import json

        data = dict(node)
        # Convert string UUIDs back to UUID objects
        for field_name, field_info in cls.model_fields.items():
            if field_name in data:
                annotation = field_info.annotation
                # Handle Optional types
                origin = getattr(annotation, "__origin__", None)
                if origin is type(None) or str(origin) == "typing.Union":
                    args = getattr(annotation, "__args__", ())
                    annotation = args[0] if args else annotation

                if annotation is UUID or (hasattr(annotation, "__origin__") and annotation.__origin__ is UUID):
                    if data[field_name] is not None:
                        data[field_name] = UUID(data[field_name])
                elif annotation is datetime:
                    if data[field_name] is not None and isinstance(data[field_name], str):
                        data[field_name] = datetime.fromisoformat(data[field_name])
        return cls.model_validate(data)

    def to_db_row(self) -> dict[str, Any]:
        """Convert model to database row format (e.g., for Supabase/PostgreSQL)."""
        data = self.model_dump()
        result = {}
        for key, value in data.items():
            if isinstance(value, UUID):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, Enum):
                result[key] = value.value
            else:
                result[key] = value
        return result

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "BaseEntity":
        """Create model instance from database row."""
        return cls.model_validate(row)


# =============================================================================
# Core Entity Models
# =============================================================================


class Business(BaseEntity):
    """Restaurant or food business entity."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., min_length=1, max_length=255, description="Business name")
    google_place_id: Optional[str] = Field(
        None, max_length=255, description="Google Places API ID"
    )
    cuisine_type: Optional[str] = Field(
        None, max_length=100, description="Primary cuisine type"
    )
    price_range: Optional[PriceRange] = Field(
        None, description="Price range indicator ($, $$, $$$, $$$$)"
    )
    avg_rating: Optional[float] = Field(
        None, ge=0.0, le=5.0, description="Average rating (0-5)"
    )
    address: str = Field(..., max_length=500, description="Street address")
    city: str = Field(..., max_length=100, description="City name")
    postcode: str = Field(..., max_length=20, description="Postal/ZIP code")
    lat: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="Latitude coordinate"
    )
    lng: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="Longitude coordinate"
    )
    phone: Optional[str] = Field(None, max_length=30, description="Phone number")
    website: Optional[str] = Field(None, max_length=500, description="Website URL")
    is_client: bool = Field(
        False, description="True if paying customer, False if competitor"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Record creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties with price_range as string."""
        props = super().to_neo4j_properties()
        if self.price_range:
            props["price_range"] = self.price_range.value
        return props


class Review(BaseEntity):
    """Customer review for a business."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    business_id: UUID = Field(..., description="Associated business ID")
    google_review_id: Optional[str] = Field(
        None, max_length=255, description="Google review ID"
    )
    platform: Platform = Field(..., description="Review source platform")
    author_name: str = Field(..., max_length=255, description="Review author name")
    text: str = Field(..., description="Review text content")
    rating: float = Field(..., ge=0.0, le=5.0, description="Rating (0-5)")
    review_date: datetime = Field(..., description="Date the review was posted")
    sentiment_score: Optional[float] = Field(
        None, ge=-1.0, le=1.0, description="Sentiment score (-1 to 1)"
    )
    themes: Optional[list[str]] = Field(
        None, description="Extracted themes/topics from review"
    )
    embedding_id: Optional[str] = Field(
        None, max_length=255, description="Pinecone vector embedding ID"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Record creation timestamp"
    )


class Competitor(BaseEntity):
    """Competitor relationship between businesses."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    client_business_id: UUID = Field(
        ..., description="The client business we're monitoring for"
    )
    competitor_business_id: UUID = Field(
        ..., description="The competitor business"
    )
    similarity_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Similarity score (0-1)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Record creation timestamp"
    )


class AnalysisReport(BaseEntity):
    """Periodic analysis report for a business."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    business_id: UUID = Field(..., description="Associated business ID")
    report_date: datetime = Field(..., description="Date the report was generated")
    period_start: datetime = Field(..., description="Analysis period start date")
    period_end: datetime = Field(..., description="Analysis period end date")
    summary: str = Field(..., description="Executive summary of the analysis")
    sentiment_trend: dict[str, Any] = Field(
        default_factory=dict, description="Sentiment trend data over the period"
    )
    top_themes: list[dict[str, Any]] = Field(
        default_factory=list, description="Top themes/topics mentioned in reviews"
    )
    competitor_comparison: dict[str, Any] = Field(
        default_factory=dict, description="Comparison with competitor metrics"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="AI-generated recommendations"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Record creation timestamp"
    )

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties, serializing complex types as JSON."""
        import json

        props = super().to_neo4j_properties()
        # Ensure complex types are JSON strings for Neo4j
        props["sentiment_trend"] = json.dumps(self.sentiment_trend)
        props["top_themes"] = json.dumps(self.top_themes)
        props["competitor_comparison"] = json.dumps(self.competitor_comparison)
        props["recommendations"] = json.dumps(self.recommendations)
        return props

    @classmethod
    def from_neo4j_node(cls, node: dict[str, Any]) -> "AnalysisReport":
        """Create from Neo4j node, deserializing JSON fields."""
        import json

        data = dict(node)
        # Parse JSON strings back to Python objects
        for field in ["sentiment_trend", "top_themes", "competitor_comparison", "recommendations"]:
            if field in data and isinstance(data[field], str):
                data[field] = json.loads(data[field])

        return super().from_neo4j_node(data)


# =============================================================================
# Request/Response Models for API
# =============================================================================


class BusinessCreate(BaseModel):
    """Request model for creating a business."""

    name: str = Field(..., min_length=1, max_length=255)
    google_place_id: Optional[str] = None
    cuisine_type: Optional[str] = None
    price_range: Optional[PriceRange] = None
    address: str
    city: str
    postcode: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    is_client: bool = False


class BusinessUpdate(BaseModel):
    """Request model for updating a business."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    google_place_id: Optional[str] = None
    cuisine_type: Optional[str] = None
    price_range: Optional[PriceRange] = None
    avg_rating: Optional[float] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    is_client: Optional[bool] = None


class ReviewCreate(BaseModel):
    """Request model for creating a review."""

    business_id: UUID
    google_review_id: Optional[str] = None
    platform: Platform
    author_name: str
    text: str
    rating: float = Field(..., ge=0.0, le=5.0)
    review_date: datetime


class CompetitorCreate(BaseModel):
    """Request model for creating a competitor relationship."""

    client_business_id: UUID
    competitor_business_id: UUID
    similarity_score: Optional[float] = None


# =============================================================================
# Response Models
# =============================================================================


class BusinessResponse(Business):
    """Response model for business with computed fields."""

    review_count: Optional[int] = Field(None, description="Total number of reviews")
    competitor_count: Optional[int] = Field(None, description="Number of tracked competitors")


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""

    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool
