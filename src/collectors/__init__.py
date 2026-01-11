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

    collector = GooglePlacesCollector(api_key=settings.google_places_api_key)
    businesses = await collector.collect(
        query="restaurants",
        location="San Francisco, CA",
        radius=5000
    )
    normalized = await collector.transform(businesses)
"""
