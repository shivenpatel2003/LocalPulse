"""Instagram client wrapper around Apify scrapers.

Provides async methods for scraping Instagram profiles, posts, and hashtags
using Apify actors with retry logic.
"""

import asyncio
import logging
import os

from apify_client import ApifyClient
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


class InstagramClient:
    """Wrapper around Apify Instagram scrapers with retry logic.

    Uses Apify actors for Instagram scraping since Instagram's anti-bot
    measures are too sophisticated for DIY scraping.

    Example:
        client = InstagramClient()
        profile = await client.scrape_profile("username")
        posts = await client.scrape_posts("username", limit=20)
    """

    # Apify actor IDs for Instagram scraping
    PROFILE_SCRAPER = "apify/instagram-profile-scraper"
    POST_SCRAPER = "apify/instagram-scraper"

    def __init__(self, api_token: str | None = None):
        """Initialize Instagram client.

        Args:
            api_token: Apify API token. If None, reads from APIFY_API_TOKEN env var.

        Raises:
            ValueError: If no API token is provided or found in environment.
        """
        token = api_token or os.environ.get("APIFY_API_TOKEN")
        if not token:
            raise ValueError(
                "Apify API token required. Set APIFY_API_TOKEN env var or pass api_token."
            )
        self.client = ApifyClient(token)
        logger.info("InstagramClient initialized")

    def _run_actor_sync(self, actor_id: str, run_input: dict) -> list[dict]:
        """Run Apify actor synchronously and return results.

        Note: Apify client is synchronous; we wrap for async interface.

        Args:
            actor_id: The Apify actor ID to run.
            run_input: Input parameters for the actor.

        Returns:
            List of result dictionaries from the actor's dataset.
        """
        run = self.client.actor(actor_id).call(run_input=run_input)
        items = list(self.client.dataset(run["defaultDatasetId"]).iterate_items())
        return items

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=60),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: logger.warning(
            f"Apify retry {retry_state.attempt_number}: {retry_state.outcome.exception()}"
        ),
    )
    async def scrape_profile(self, username: str) -> dict | None:
        """Scrape Instagram profile.

        Args:
            username: Instagram username (without @)

        Returns:
            Profile dictionary or None if not found
        """
        run_input = {
            "usernames": [username],
            "resultsType": "details",
        }

        logger.info(f"Scraping Instagram profile: @{username}")

        # Run in thread pool since Apify client is synchronous
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(
            None, self._run_actor_sync, self.PROFILE_SCRAPER, run_input
        )

        return items[0] if items else None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=60),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: logger.warning(
            f"Apify retry {retry_state.attempt_number}: {retry_state.outcome.exception()}"
        ),
    )
    async def scrape_posts(self, username: str, limit: int = 50) -> list[dict]:
        """Scrape user's posts.

        Args:
            username: Instagram username (without @)
            limit: Maximum number of posts to return

        Returns:
            List of post dictionaries
        """
        run_input = {
            "usernames": [username],
            "resultsType": "posts",
            "resultsLimit": limit,
        }

        logger.info(f"Scraping Instagram posts: @{username} (limit={limit})")

        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(
            None, self._run_actor_sync, self.POST_SCRAPER, run_input
        )

        return items

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=60),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: logger.warning(
            f"Apify retry {retry_state.attempt_number}: {retry_state.outcome.exception()}"
        ),
    )
    async def scrape_hashtag(self, hashtag: str, limit: int = 100) -> list[dict]:
        """Scrape posts by hashtag.

        Args:
            hashtag: Hashtag to search (without #)
            limit: Maximum number of posts to return

        Returns:
            List of post dictionaries
        """
        run_input = {
            "hashtags": [hashtag],
            "resultsType": "posts",
            "resultsLimit": limit,
        }

        logger.info(f"Scraping Instagram hashtag: #{hashtag} (limit={limit})")

        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(
            None, self._run_actor_sync, self.POST_SCRAPER, run_input
        )

        return items
