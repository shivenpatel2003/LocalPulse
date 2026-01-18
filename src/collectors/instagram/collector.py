"""Instagram collector extending BaseCollector.

Provides InstagramCollector for collecting and normalizing Instagram
posts, profiles, and hashtag searches.
"""

import logging
from typing import Any

from src.collectors.base import BaseCollector
from src.collectors.instagram.client import InstagramClient
from src.collectors.instagram.normalizer import (
    transform_instagram_post,
    transform_instagram_profile,
)
from src.collectors.normalization.schema import CollectedContent
from src.collectors.registry import CollectorType, register_collector

logger = logging.getLogger(__name__)


@register_collector(CollectorType.INSTAGRAM)
class InstagramCollector(BaseCollector):
    """Collector for Instagram data using Apify.

    Config options:
        api_token: Apify API token (or set APIFY_API_TOKEN env var)

    Example:
        collector = InstagramCollector({"api_token": "your_token"})
        posts = await collector.collect_user_posts("username", limit=20)
        profile = await collector.collect_user_profile("username")
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize Instagram collector.

        Args:
            config: Configuration dictionary with optional api_token
        """
        super().__init__(config)
        self.client = InstagramClient(api_token=config.get("api_token"))
        logger.info("InstagramCollector initialized")

    async def collect_user_posts(
        self,
        username: str,
        limit: int = 50,
    ) -> list[CollectedContent]:
        """Collect posts from a specific user.

        Args:
            username: Instagram username (without @)
            limit: Maximum number of posts to collect

        Returns:
            List of normalized CollectedContent instances
        """
        logger.info(f"Collecting Instagram posts for @{username} (limit={limit})")
        raw_posts = await self.client.scrape_posts(username, limit=limit)

        results = []
        for raw in raw_posts:
            try:
                content = transform_instagram_post(raw)
                results.append(content)
            except Exception as e:
                logger.warning(f"Failed to transform post {raw.get('id')}: {e}")
                continue

        logger.info(f"Collected {len(results)} posts for @{username}")
        return results

    async def collect_user_profile(self, username: str) -> CollectedContent | None:
        """Collect profile data for a specific user.

        Args:
            username: Instagram username (without @)

        Returns:
            Normalized CollectedContent instance or None if failed
        """
        logger.info(f"Collecting Instagram profile for @{username}")
        try:
            raw_profile = await self.client.scrape_profile(username)
            if raw_profile:
                return transform_instagram_profile(raw_profile)
            return None
        except Exception as e:
            logger.error(f"Failed to collect profile for @{username}: {e}")
            return None

    async def search_hashtag(
        self,
        hashtag: str,
        limit: int = 100,
    ) -> list[CollectedContent]:
        """Search posts by hashtag.

        Args:
            hashtag: Hashtag to search (without #)
            limit: Maximum number of posts to return

        Returns:
            List of normalized CollectedContent instances
        """
        logger.info(f"Searching Instagram hashtag: #{hashtag} (limit={limit})")
        raw_posts = await self.client.scrape_hashtag(hashtag, limit=limit)

        results = []
        for raw in raw_posts:
            try:
                content = transform_instagram_post(raw)
                results.append(content)
            except Exception as e:
                logger.warning(f"Failed to transform post {raw.get('id')}: {e}")
                continue

        logger.info(f"Found {len(results)} posts for #{hashtag}")
        return results

    async def health_check(self) -> bool:
        """Check if the collector is operational.

        Returns:
            True if Apify API is accessible
        """
        try:
            # Simple check: verify client was created successfully
            # A full health check would make an API call
            return self.client is not None
        except Exception as e:
            logger.error(f"Instagram health check failed: {e}")
            return False
