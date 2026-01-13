"""
Data Models and Schemas.

This module defines all data structures used throughout LocalPulse:

- entities: Core domain entities (Business, Review, Competitor, Location)
- schemas: Pydantic models for API request/response validation
- state: LangGraph state definitions for workflow management

Entity Hierarchy:
- Business: Restaurant or food establishment
- Review: Customer review with sentiment and topics
- Competitor: Competitive relationship between businesses
- Location: Geographic location with coordinates
- Cuisine: Food type/category classification
- Event: Local events that may impact business

Example:
    from src.models import Business, Review, AgentState

    business = Business(
        id="123",
        name="Local Bistro",
        location=Location(lat=37.7749, lng=-122.4194)
    )

    state = AgentState(
        messages=[],
        current_agent="supervisor",
        iteration=0
    )
"""

from src.models.schemas import (
    AnalysisReport,
    Business,
    BusinessCreate,
    BusinessResponse,
    BusinessUpdate,
    Competitor,
    CompetitorCreate,
    PaginatedResponse,
    Platform,
    PriceRange,
    Review,
    ReviewCreate,
)

__all__ = [
    # Enums
    "Platform",
    "PriceRange",
    # Core entities
    "Business",
    "Review",
    "Competitor",
    "AnalysisReport",
    # Request models
    "BusinessCreate",
    "BusinessUpdate",
    "ReviewCreate",
    "CompetitorCreate",
    # Response models
    "BusinessResponse",
    "PaginatedResponse",
]
