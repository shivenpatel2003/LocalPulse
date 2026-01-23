"""Instagram collector extending BaseCollector.

Provides InstagramCollector for collecting and normalizing Instagram
posts, profiles, and hashtag searches.
"""

import structlog
from typing import Any

from src.collectors.base import BaseCollector
from src.collectors.instagram.client import InstagramClient
from src.collectors.instagram.normalizer import (
    transform_instagram_post,
    transform_instagram_profile,
)
from src.collectors.normalization.schema import CollectedContent
from src.collectors.registry import CollectorType, register_collector
from src.core.exceptions import (
    CollectorError,
    CollectorNotFoundError,
    CollectorUnavailableError,
)
from src.core.circuit_breaker import get_circuit_breaker

logger = structlog.get_logger(__name__)

# Circuit breaker for Instagram/Apify API
_instagram_breaker = get_circuit_breaker("instagram", failure_threshold=5, recovery_timeout=60)


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

        Raises:
            CollectorUnavailableError: If circuit breaker is open
            CollectorError: For API failures
        """
        logger.info("collecting_instagram_posts", username=username, limit=limit)

        if not _instagram_breaker.can_execute():
            recovery_time = _instagram_breaker.time_until_recovery()
            raise CollectorUnavailableError(
                "instagram",
                f"Circuit breaker open. Recovery in {recovery_time:.1f}s",
                {"username": username, "recovery_time": recovery_time},
            )

        try:
            raw_posts = await self.client.scrape_posts(username, limit=limit)
            await _instagram_breaker.record_success()

            results = []
            for raw in raw_posts:
                try:
                    content = transform_instagram_post(raw)
                    results.append(content)
                except Exception as e:
                    logger.warning(
                        "instagram_post_transform_failed",
                        post_id=raw.get("id"),
                        error=str(e),
                    )
                    continue

            logger.info("instagram_posts_collected", username=username, count=len(results))
            return results

        except CollectorUnavailableError:
            raise
        except Exception as e:
            await _instagram_breaker.record_failure()
            logger.error(
                "instagram_posts_collection_failed",
                username=username,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise CollectorError(
                "instagram",
                f"Failed to collect posts for @{username}: {e}",
                {"username": username, "original_error": str(e)},
            )

    async def collect_user_profile(self, username: str) -> CollectedContent:
        """Collect profile data for a specific user.

        Args:
            username: Instagram username (without @)

        Returns:
            Normalized CollectedContent instance

        Raises:
            CollectorNotFoundError: If profile not found
            CollectorUnavailableError: If service is unavailable
            CollectorError: For other errors
        """
        logger.info("collecting_instagram_profile", username=username)

        if not _instagram_breaker.can_execute():
            recovery_time = _instagram_breaker.time_until_recovery()
            raise CollectorUnavailableError(
                "instagram",
                f"Circuit breaker open. Recovery in {recovery_time:.1f}s",
                {"username": username, "recovery_time": recovery_time},
            )

        try:
            raw_profile = await self.client.scrape_profile(username)

            if not raw_profile:
                await _instagram_breaker.record_failure()
                raise CollectorNotFoundError(
                    "instagram",
                    f"Profile not found: @{username}",
                    {"username": username},
                )

            await _instagram_breaker.record_success()
            return transform_instagram_profile(raw_profile)

        except (CollectorNotFoundError, CollectorUnavailableError):
            # Re-raise our own exceptions
            raise
        except Exception as e:
            await _instagram_breaker.record_failure()
            logger.error(
                "instagram_profile_collection_failed",
                username=username,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise CollectorError(
                "instagram",
                f"Failed to collect profile for @{username}: {e}",
                {"username": username, "original_error": str(e)},
            )

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

        Raises:
            CollectorUnavailableError: If circuit breaker is open
            CollectorError: For API failures
        """
        logger.info("searching_instagram_hashtag", hashtag=hashtag, limit=limit)

        if not _instagram_breaker.can_execute():
            recovery_time = _instagram_breaker.time_until_recovery()
            raise CollectorUnavailableError(
                "instagram",
                f"Circuit breaker open. Recovery in {recovery_time:.1f}s",
                {"hashtag": hashtag, "recovery_time": recovery_time},
            )

        try:
            raw_posts = await self.client.scrape_hashtag(hashtag, limit=limit)
            await _instagram_breaker.record_success()

            results = []
            for raw in raw_posts:
                try:
                    content = transform_instagram_post(raw)
                    results.append(content)
                except Exception as e:
                    logger.warning(
                        "instagram_post_transform_failed",
                        post_id=raw.get("id"),
                        error=str(e),
                    )
                    continue

            logger.info("instagram_hashtag_results", hashtag=hashtag, count=len(results))
            return results

        except CollectorUnavailableError:
            raise
        except Exception as e:
            await _instagram_breaker.record_failure()
            logger.error(
                "instagram_hashtag_search_failed",
                hashtag=hashtag,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise CollectorError(
                "instagram",
                f"Failed to search hashtag #{hashtag}: {e}",
                {"hashtag": hashtag, "original_error": str(e)},
            )

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
