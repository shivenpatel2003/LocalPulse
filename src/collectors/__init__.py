"""
Collectors Module

This module contains data collection agents for various sources:
- GooglePlacesCollector: Collects business data from Google Places API
- ReviewCollector: Aggregates reviews from multiple platforms
- SocialMediaCollector: Monitors social media mentions
- MenuCollector: Extracts and tracks menu information
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseCollector
    from .google_places import GooglePlacesCollector
    from .reviews import ReviewCollector

__all__ = [
    "BaseCollector",
    "GooglePlacesCollector",
    "ReviewCollector",
]
