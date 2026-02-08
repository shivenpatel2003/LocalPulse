"""Outscraper service for fetching Google Reviews.

Uses the Outscraper Reviews API v3 to fetch richer review data than
the Google Places API (which is limited to 5 reviews).

API Docs: https://app.outscraper.com/api-docs#tag/Google-Reviews
Free tier: 500 reviews/month.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import httpx
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

OUTSCRAPER_REVIEWS_URL = "https://api.app.outscraper.com/maps/reviews-v3"


class OutscraperService:
    """Service for fetching reviews via Outscraper API."""

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self._api_key = api_key or (
            settings.outscraper_api_key.get_secret_value()
            if settings.outscraper_api_key
            else None
        )

    @property
    def is_configured(self) -> bool:
        """Check if the Outscraper API key is available."""
        return self._api_key is not None

    async def fetch_reviews(
        self,
        query: str,
        limit: int = 30,
        sort: str = "newest_first",
    ) -> list[dict[str, Any]]:
        """Fetch Google Reviews for a business via Outscraper.

        Args:
            query: Business name + location (e.g. "Dishoom King's Cross, London")
                   OR a Google place_id.
            limit: Maximum number of reviews to fetch.
            sort: Sort order - "newest_first" or "most_relevant".

        Returns:
            List of normalized review dicts matching the pipeline format:
            {type, id, author_name, rating, text, time, platform, ...}
            Returns empty list on any failure.
        """
        if not self._api_key:
            logger.warning("outscraper_not_configured")
            return []

        logger.info(
            "outscraper_fetch_reviews",
            query=query,
            limit=limit,
            sort=sort,
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(
                    OUTSCRAPER_REVIEWS_URL,
                    headers={"X-API-KEY": self._api_key},
                    params={
                        "query": query,
                        "reviewsLimit": limit,
                        "sort": sort,
                        "language": "en",
                        "async": "false",
                    },
                )

                if resp.status_code != 200:
                    logger.error(
                        "outscraper_api_error",
                        status=resp.status_code,
                        body=resp.text[:300],
                    )
                    return []

                data = resp.json()

                # --- DEBUG: log raw response structure ---
                logger.info(
                    "outscraper_debug_response",
                    response_type=type(data).__name__,
                    top_level_keys=list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]",
                )

                # Outscraper returns different formats depending on async mode:
                #   async mode:  {"id": "...", "status": "Success", "data": [[{...}]]}
                #   sync mode:   [{name: "...", "reviews_data": [...]}]
                place_data = None

                if isinstance(data, list):
                    # Sync mode: response is a direct list of place results
                    logger.info(
                        "outscraper_debug_sync_format",
                        list_length=len(data),
                        first_item_type=type(data[0]).__name__ if data else "empty",
                        first_item_keys=list(data[0].keys())[:10] if data and isinstance(data[0], dict) else "N/A",
                    )
                    if data and isinstance(data[0], dict):
                        place_data = data[0]
                    elif data and isinstance(data[0], list) and data[0]:
                        # Nested: [[{...}]]
                        place_data = data[0][0] if isinstance(data[0][0], dict) else None

                elif isinstance(data, dict):
                    # Async wrapper mode: {"status": "Success", "data": [[{...}]]}
                    logger.info(
                        "outscraper_debug_async_format",
                        status=data.get("status"),
                        data_type=type(data.get("data")).__name__ if "data" in data else "missing",
                    )
                    if data.get("status") != "Success":
                        logger.warning(
                            "outscraper_not_success",
                            status=data.get("status"),
                        )
                        return []

                    results = data.get("data", [])
                    if not results or not results[0]:
                        logger.info("outscraper_no_results", query=query)
                        return []

                    inner = results[0]
                    if isinstance(inner, list):
                        place_data = inner[0] if inner else None
                    elif isinstance(inner, dict):
                        place_data = inner

                if not place_data:
                    logger.info("outscraper_no_place_data", query=query)
                    return []

                # --- DEBUG: log place_data structure ---
                logger.info(
                    "outscraper_debug_place_data",
                    place_name=place_data.get("name", "N/A"),
                    place_keys=list(place_data.keys())[:15],
                    reviews_data_count=len(place_data.get("reviews_data", [])),
                )

                raw_reviews = place_data.get("reviews_data", [])
                if not raw_reviews:
                    logger.info(
                        "outscraper_no_reviews",
                        query=query,
                        place_keys=list(place_data.keys())[:15],
                    )
                    return []

                # Normalize to pipeline format
                normalized = self._normalize_reviews(raw_reviews)

                logger.info(
                    "outscraper_reviews_fetched",
                    query=query,
                    count=len(normalized),
                )

                return normalized

        except httpx.TimeoutException:
            logger.error("outscraper_timeout", query=query)
            return []
        except Exception as e:
            logger.error("outscraper_error", error=str(e), query=query)
            return []

    def _normalize_reviews(
        self,
        raw_reviews: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Normalize Outscraper review format to pipeline format.

        Outscraper fields: author_title, review_text, review_rating,
        review_datetime_utc, review_likes, owner_answer,
        owner_answer_timestamp_datetime_utc.

        Pipeline fields: type, id, author_name, rating, text, time,
        platform, review_likes, owner_response.
        """
        normalized = []
        for raw in raw_reviews:
            text = raw.get("review_text") or ""
            if not text.strip():
                continue  # Skip reviews with no text

            review = {
                "type": "review",
                "id": str(uuid4()),
                "author_name": raw.get("author_title", "Anonymous"),
                "rating": raw.get("review_rating"),
                "text": text,
                "time": raw.get("review_datetime_utc"),
                "platform": "google",
                "source": "outscraper",
                "review_likes": raw.get("review_likes", 0),
                "owner_response": raw.get("owner_answer"),
                "owner_response_time": raw.get(
                    "owner_answer_timestamp_datetime_utc"
                ),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
            normalized.append(review)

        return normalized

    async def fetch_competitor_reviews(
        self,
        competitors: list[dict[str, Any]],
        reviews_per_competitor: int = 15,
        max_competitors: int = 3,
    ) -> list[dict[str, Any]]:
        """Fetch reviews for competitor businesses.

        Args:
            competitors: List of competitor dicts with 'name' and
                         optionally 'google_place_id' and 'address'.
            reviews_per_competitor: Reviews to fetch per competitor.
            max_competitors: Maximum number of competitors to fetch for.

        Returns:
            Updated competitor dicts with 'reviews' field added.
        """
        if not self._api_key:
            logger.warning("outscraper_not_configured_for_competitors")
            return competitors

        updated = []
        fetched_count = 0

        for comp in competitors:
            if fetched_count >= max_competitors:
                updated.append(comp)
                continue

            # Build query - prefer google_place_id, fallback to name+address
            place_id = comp.get("google_place_id", "")
            if place_id and place_id.startswith("places/"):
                # Outscraper doesn't use places/ prefix
                place_id = place_id.replace("places/", "")

            name = comp.get("name", "")
            address = comp.get("address", "")

            if place_id:
                query = place_id
            elif name and address:
                query = f"{name}, {address}"
            elif name:
                query = name
            else:
                updated.append(comp)
                continue

            logger.info(
                "outscraper_fetch_competitor_reviews",
                competitor=name,
                query=query[:80],
            )

            reviews = await self.fetch_reviews(
                query=query,
                limit=reviews_per_competitor,
                sort="newest_first",
            )

            comp_with_reviews = dict(comp)
            comp_with_reviews["reviews"] = reviews
            comp_with_reviews["review_count"] = len(reviews)
            updated.append(comp_with_reviews)
            fetched_count += 1

        logger.info(
            "outscraper_competitor_reviews_complete",
            competitors_fetched=fetched_count,
            total_competitors=len(competitors),
        )

        return updated
