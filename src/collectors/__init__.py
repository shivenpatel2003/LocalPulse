"""
Data Source Integrations.

This module contains collectors for gathering data from external sources:

- google_places: Google Places API for business info, reviews, and photos
- social: Social media monitoring (Instagram, Twitter/X mentions)
- events: Local event aggregation (concerts, festivals, community events)
- scraper: Web scraping utilities for additional data sources

Collectors follow a common interface with async methods:
- collect(): Fetch raw data from the source
- transform(): Normalize data to internal schemas
- validate(): Ensure data quality and completeness

Example:
    from src.collectors import GooglePlacesCollector

    async with GooglePlacesCollector() as collector:
        places = await collector.search_places("Italian restaurant", "Manchester, UK")
        details = await collector.get_place_details(places[0]["id"])
        reviews = await collector.get_place_reviews(places[0]["id"])
        competitors = await collector.find_nearby_competitors(places[0]["id"])
"""

from src.collectors.google_places import (
    GooglePlacesCollector,
    GooglePlacesError,
    GooglePlacesAuthError,
    GooglePlacesRateLimitError,
    GooglePlacesNotFoundError,
    test_google_places,
)

__all__ = [
    "GooglePlacesCollector",
    "GooglePlacesError",
    "GooglePlacesAuthError",
    "GooglePlacesRateLimitError",
    "GooglePlacesNotFoundError",
    "test_google_places",
]
