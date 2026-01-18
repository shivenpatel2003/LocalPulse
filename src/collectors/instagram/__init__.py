"""Instagram data collector module.

Provides InstagramClient for Apify integration, InstagramCollector
extending BaseCollector, and normalizer functions.
"""

from src.collectors.instagram.client import InstagramClient
from src.collectors.instagram.collector import InstagramCollector
from src.collectors.instagram.normalizer import (
    transform_instagram_post,
    transform_instagram_profile,
)

__all__ = [
    "InstagramClient",
    "InstagramCollector",
    "transform_instagram_post",
    "transform_instagram_profile",
]
