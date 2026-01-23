"""Google Places API (New) collector for business and review data.

This module provides async methods to search for places, get details,
fetch reviews, and find nearby competitors using the Places API (New).

API Reference: https://developers.google.com/maps/documentation/places/web-service/op-overview
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import get_settings
from src.core.circuit_breaker import get_circuit_breaker
from src.core.exceptions import (
    CollectorAuthError,
    CollectorError,
    CollectorNotFoundError,
    CollectorRateLimitError,
    CollectorTimeoutError,
    CollectorUnavailableError,
)
from src.models.schemas import Business, Platform, PriceRange, Review

logger = structlog.get_logger(__name__)

# Circuit breaker for Google Places API
_google_places_breaker = get_circuit_breaker("google_places", failure_threshold=5, recovery_timeout=60)


# =============================================================================
# Constants
# =============================================================================

PLACES_API_BASE = "https://places.googleapis.com/v1"

# Field masks for API requests (controls what data is returned)
PLACE_BASIC_FIELDS = [
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
]

PLACE_DETAIL_FIELDS = [
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "rating",
    "userRatingCount",
    "priceLevel",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "websiteUri",
    "regularOpeningHours",
    "primaryType",
    "types",
]

PLACE_REVIEW_FIELDS = [
    "id",
    "displayName",
    "formattedAddress",
    "rating",
    "reviews",
]

# Price level mapping from Google API to our enum
PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE": PriceRange.BUDGET,
    "PRICE_LEVEL_INEXPENSIVE": PriceRange.BUDGET,
    "PRICE_LEVEL_MODERATE": PriceRange.MODERATE,
    "PRICE_LEVEL_EXPENSIVE": PriceRange.UPSCALE,
    "PRICE_LEVEL_VERY_EXPENSIVE": PriceRange.FINE_DINING,
}


# =============================================================================
# Exceptions
# =============================================================================


class GooglePlacesError(Exception):
    """Base exception for Google Places API errors."""

    pass


class GooglePlacesRateLimitError(GooglePlacesError):
    """Raised when rate limited by Google Places API."""

    pass


class GooglePlacesAuthError(GooglePlacesError):
    """Raised when authentication fails."""

    pass


class GooglePlacesNotFoundError(GooglePlacesError):
    """Raised when a place is not found."""

    pass


# =============================================================================
# Google Places Collector
# =============================================================================


class GooglePlacesCollector:
    """Async collector for Google Places API (New).

    This collector uses the new Places API which provides improved
    functionality and field-based billing.

    Example:
        collector = GooglePlacesCollector()
        async with collector:
            places = await collector.search_places("Italian restaurant", "Manchester, UK")
            if places:
                details = await collector.get_place_details(places[0]["id"])
                reviews = await collector.get_place_reviews(places[0]["id"])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """Initialize the collector.

        Args:
            api_key: Google Places API key. If not provided, loads from settings.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for failed requests.
        """
        settings = get_settings()
        self._api_key = api_key or (
            settings.google_places_api_key.get_secret_value()
            if settings.google_places_api_key
            else None
        )
        if not self._api_key:
            raise GooglePlacesAuthError("Google Places API key not configured")

        self._timeout = timeout
        self._max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

        # Rate limiting: track requests per second
        self._request_times: list[float] = []
        self._max_requests_per_second = 10  # Google's default QPS limit

    async def __aenter__(self) -> "GooglePlacesCollector":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            headers={
                "X-Goog-Api-Key": self._api_key,
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _rate_limit(self) -> None:
        """Enforce rate limiting to respect Google's QPS limits."""
        now = asyncio.get_event_loop().time()

        # Remove timestamps older than 1 second
        self._request_times = [t for t in self._request_times if now - t < 1.0]

        # If at limit, wait until oldest request expires
        if len(self._request_times) >= self._max_requests_per_second:
            wait_time = 1.0 - (now - self._request_times[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        self._request_times.append(now)

    @retry(
        retry=retry_if_exception_type((GooglePlacesRateLimitError, CollectorRateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: Optional[dict] = None,
        field_mask: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Make an API request with rate limiting, circuit breaker, and retries.

        Args:
            method: HTTP method (GET, POST).
            endpoint: API endpoint path.
            json_data: JSON body for POST requests.
            field_mask: Fields to include in response.

        Returns:
            Parsed JSON response.

        Raises:
            CollectorUnavailableError: When circuit breaker is open.
            CollectorRateLimitError: When rate limited.
            CollectorAuthError: On authentication failure.
            CollectorNotFoundError: When resource not found.
            CollectorError: On other API errors.
        """
        # Check circuit breaker first
        if not _google_places_breaker.can_execute():
            recovery_time = _google_places_breaker.time_until_recovery()
            logger.warning(
                "google_places_circuit_open",
                recovery_time=recovery_time,
                endpoint=endpoint,
            )
            raise CollectorUnavailableError(
                "google_places",
                f"Circuit breaker open. Recovery in {recovery_time:.1f}s",
                {"endpoint": endpoint, "recovery_time": recovery_time},
            )

        await self._rate_limit()
        client = await self._ensure_client()

        url = f"{PLACES_API_BASE}/{endpoint}"

        headers = {}
        if field_mask:
            headers["X-Goog-FieldMask"] = ",".join(field_mask)

        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers)
            else:
                response = await client.post(url, json=json_data, headers=headers)

            # Handle specific error codes
            if response.status_code == 429:
                await _google_places_breaker.record_failure()
                logger.warning("google_places_rate_limited", endpoint=endpoint)
                raise CollectorRateLimitError(
                    "google_places",
                    "Rate limited by Google Places API",
                    {"endpoint": endpoint},
                )
            elif response.status_code == 401:
                await _google_places_breaker.record_failure()
                raise CollectorAuthError(
                    "google_places",
                    "Invalid API key",
                    {"endpoint": endpoint},
                )
            elif response.status_code == 403:
                await _google_places_breaker.record_failure()
                raise CollectorAuthError(
                    "google_places",
                    "API key not authorized for Places API",
                    {"endpoint": endpoint},
                )
            elif response.status_code == 404:
                # 404 is not a circuit breaker failure - it's expected for missing resources
                raise CollectorNotFoundError(
                    "google_places",
                    f"Resource not found: {endpoint}",
                    {"endpoint": endpoint},
                )
            elif response.status_code >= 400:
                await _google_places_breaker.record_failure()
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                logger.error(
                    "google_places_api_error",
                    status_code=response.status_code,
                    error=error_msg,
                    endpoint=endpoint,
                )
                raise CollectorError(
                    "google_places",
                    f"API error {response.status_code}: {error_msg}",
                    {"endpoint": endpoint, "status_code": response.status_code},
                )

            # Success - record it
            await _google_places_breaker.record_success()
            return response.json() if response.content else {}

        except httpx.TimeoutException as e:
            await _google_places_breaker.record_failure()
            logger.error("google_places_timeout", endpoint=endpoint, error=str(e))
            raise CollectorTimeoutError(
                "google_places",
                f"Request timeout: {e}",
                {"endpoint": endpoint},
            )
        except httpx.RequestError as e:
            await _google_places_breaker.record_failure()
            logger.error("google_places_request_error", endpoint=endpoint, error=str(e))
            raise CollectorError(
                "google_places",
                f"Request failed: {e}",
                {"endpoint": endpoint, "original_error": str(e)},
            )

    # -------------------------------------------------------------------------
    # Public API Methods
    # -------------------------------------------------------------------------

    async def search_places(
        self,
        query: str,
        location: str,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for places by text query and location.

        Uses the Text Search (New) endpoint to find businesses.

        Args:
            query: Search query (e.g., "Italian restaurant").
            location: Location text (e.g., "Manchester, UK").
            max_results: Maximum number of results to return.

        Returns:
            List of place dictionaries with id, name, address, location.

        Example:
            places = await collector.search_places(
                "Italian restaurant",
                "Manchester, UK"
            )
        """
        data = {
            "textQuery": f"{query} in {location}",
            "maxResultCount": min(max_results, 20),  # API max is 20
            "languageCode": "en",
        }

        response = await self._request(
            "POST",
            "places:searchText",
            json_data=data,
            field_mask=PLACE_BASIC_FIELDS,
        )

        places = response.get("places", [])
        return [
            {
                "id": place.get("id"),
                "name": place.get("displayName", {}).get("text"),
                "address": place.get("formattedAddress"),
                "lat": place.get("location", {}).get("latitude"),
                "lng": place.get("location", {}).get("longitude"),
            }
            for place in places
        ]

    async def get_place_details(self, place_id: str) -> dict[str, Any]:
        """Get detailed information about a place.

        Args:
            place_id: Google Place ID (e.g., "places/ChIJ...").

        Returns:
            Dictionary with full business details.

        Example:
            details = await collector.get_place_details("places/ChIJ...")
        """
        # Ensure place_id has correct format
        if not place_id.startswith("places/"):
            place_id = f"places/{place_id}"

        response = await self._request(
            "GET",
            place_id,
            field_mask=PLACE_DETAIL_FIELDS,
        )

        # Parse opening hours if present
        opening_hours = None
        if "regularOpeningHours" in response:
            hours_data = response["regularOpeningHours"]
            opening_hours = {
                "weekday_text": hours_data.get("weekdayDescriptions", []),
                "open_now": hours_data.get("openNow"),
            }

        # Map price level
        price_level = response.get("priceLevel")
        price_range = PRICE_LEVEL_MAP.get(price_level) if price_level else None

        return {
            "id": response.get("id"),
            "name": response.get("displayName", {}).get("text"),
            "address": response.get("formattedAddress"),
            "lat": response.get("location", {}).get("latitude"),
            "lng": response.get("location", {}).get("longitude"),
            "rating": response.get("rating"),
            "user_rating_count": response.get("userRatingCount"),
            "price_level": price_level,
            "price_range": price_range.value if price_range else None,
            "phone": response.get("nationalPhoneNumber")
            or response.get("internationalPhoneNumber"),
            "website": response.get("websiteUri"),
            "opening_hours": opening_hours,
            "primary_type": response.get("primaryType"),
            "types": response.get("types", []),
        }

    async def get_place_reviews(
        self,
        place_id: str,
        max_reviews: int = 5,
    ) -> list[dict[str, Any]]:
        """Get reviews for a place.

        Note: The Places API (New) returns up to 5 most relevant reviews.

        Args:
            place_id: Google Place ID.
            max_reviews: Maximum reviews to return (API limit is 5).

        Returns:
            List of review dictionaries.

        Example:
            reviews = await collector.get_place_reviews("places/ChIJ...")
        """
        # Ensure place_id has correct format
        if not place_id.startswith("places/"):
            place_id = f"places/{place_id}"

        response = await self._request(
            "GET",
            place_id,
            field_mask=PLACE_REVIEW_FIELDS,
        )

        reviews = response.get("reviews", [])[:max_reviews]
        return [
            {
                "google_review_id": None,  # Not available in new API
                "author_name": review.get("authorAttribution", {}).get("displayName"),
                "author_uri": review.get("authorAttribution", {}).get("uri"),
                "author_photo": review.get("authorAttribution", {}).get("photoUri"),
                "rating": review.get("rating"),
                "text": review.get("text", {}).get("text", ""),
                "language": review.get("text", {}).get("languageCode"),
                "time": review.get("publishTime"),
                "relative_time": review.get("relativePublishTimeDescription"),
            }
            for review in reviews
        ]

    async def find_nearby_competitors(
        self,
        place_id: str,
        radius_meters: int = 1000,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Find nearby competitors (similar businesses).

        First gets the place details to determine type and location,
        then searches for nearby places of the same type.

        Args:
            place_id: Google Place ID of the reference business.
            radius_meters: Search radius in meters (default 1000m).
            max_results: Maximum number of competitors to return.

        Returns:
            List of competitor place dictionaries.

        Example:
            competitors = await collector.find_nearby_competitors(
                "places/ChIJ...",
                radius_meters=1500
            )
        """
        # Get the reference place details first
        details = await self.get_place_details(place_id)

        if not details.get("lat") or not details.get("lng"):
            raise GooglePlacesError("Place location not available")

        # Get the primary type for filtering
        primary_type = details.get("primary_type", "restaurant")

        # Build nearby search request
        data = {
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": details["lat"],
                        "longitude": details["lng"],
                    },
                    "radius": float(radius_meters),
                }
            },
            "includedTypes": [primary_type],
            "maxResultCount": min(max_results, 20),
            "languageCode": "en",
        }

        response = await self._request(
            "POST",
            "places:searchNearby",
            json_data=data,
            field_mask=PLACE_BASIC_FIELDS,
        )

        # Filter out the reference place itself
        reference_id = place_id if place_id.startswith("places/") else f"places/{place_id}"
        places = [
            p for p in response.get("places", [])
            if p.get("id") != reference_id and p.get("id") != details.get("id")
        ]

        return [
            {
                "id": place.get("id"),
                "name": place.get("displayName", {}).get("text"),
                "address": place.get("formattedAddress"),
                "lat": place.get("location", {}).get("latitude"),
                "lng": place.get("location", {}).get("longitude"),
            }
            for place in places
        ]

    # -------------------------------------------------------------------------
    # Conversion to Pydantic Models
    # -------------------------------------------------------------------------

    def to_business_model(
        self,
        place_data: dict[str, Any],
        is_client: bool = False,
    ) -> Business:
        """Convert place data to Business Pydantic model.

        Args:
            place_data: Dictionary from get_place_details().
            is_client: Whether this is a client business.

        Returns:
            Business model instance.
        """
        # Parse address components
        address = place_data.get("address", "")
        address_parts = address.split(", ") if address else []

        # Try to extract city and postcode (UK format typically)
        city = ""
        postcode = ""
        if len(address_parts) >= 2:
            # Usually format is: "Street, City PostCode, Country"
            city_postcode = address_parts[-2] if len(address_parts) >= 3 else address_parts[-1]
            parts = city_postcode.split()
            if parts:
                # Check if last part looks like a UK postcode
                if len(parts) >= 2 and len(parts[-1]) <= 4 and len(parts[-2]) <= 4:
                    postcode = f"{parts[-2]} {parts[-1]}"
                    city = " ".join(parts[:-2])
                else:
                    city = city_postcode

        # Map price range
        price_range = None
        if place_data.get("price_range"):
            try:
                price_range = PriceRange(place_data["price_range"])
            except ValueError:
                pass

        return Business(
            id=uuid4(),
            name=place_data.get("name", "Unknown"),
            google_place_id=place_data.get("id"),
            cuisine_type=place_data.get("primary_type"),
            price_range=price_range,
            avg_rating=place_data.get("rating"),
            address=address,
            city=city or "Unknown",
            postcode=postcode or "Unknown",
            lat=place_data.get("lat"),
            lng=place_data.get("lng"),
            phone=place_data.get("phone"),
            website=place_data.get("website"),
            is_client=is_client,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def to_review_model(
        self,
        review_data: dict[str, Any],
        business_id: str,
    ) -> Review:
        """Convert review data to Review Pydantic model.

        Args:
            review_data: Dictionary from get_place_reviews().
            business_id: UUID of the associated business.

        Returns:
            Review model instance.
        """
        # Parse review time
        review_time = review_data.get("time")
        if review_time:
            try:
                review_date = datetime.fromisoformat(review_time.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                review_date = datetime.now(timezone.utc)
        else:
            review_date = datetime.now(timezone.utc)

        return Review(
            id=uuid4(),
            business_id=business_id,
            google_review_id=review_data.get("google_review_id"),
            platform=Platform.GOOGLE,
            author_name=review_data.get("author_name", "Anonymous"),
            text=review_data.get("text", ""),
            rating=float(review_data.get("rating", 0)),
            review_date=review_date,
            sentiment_score=None,  # To be filled by analysis
            themes=None,  # To be filled by analysis
            embedding_id=None,  # To be filled after vectorization
            created_at=datetime.now(timezone.utc),
        )


# =============================================================================
# Test Function
# =============================================================================


def _safe_print(text: str) -> None:
    """Print text safely, replacing problematic Unicode characters."""
    # Replace common problematic characters
    safe_text = text.encode("ascii", errors="replace").decode("ascii")
    print(safe_text)


async def test_google_places():
    """Test the Google Places collector with a sample search.

    Searches for Italian restaurants in Manchester, gets details and reviews
    for the first result, and finds nearby competitors.
    """
    _safe_print("=" * 60)
    _safe_print("Google Places API Test")
    _safe_print("=" * 60)

    try:
        async with GooglePlacesCollector() as collector:
            # 1. Search for Italian restaurants in Manchester
            _safe_print("\n1. Searching for 'Italian restaurant Manchester'...")
            places = await collector.search_places(
                "Italian restaurant",
                "Manchester, UK"
            )

            if not places:
                _safe_print("No places found!")
                return

            _safe_print(f"   Found {len(places)} places:")
            for i, place in enumerate(places[:5], 1):
                _safe_print(f"   {i}. {place['name']}")
                _safe_print(f"      Address: {place['address']}")

            # 2. Get details for the first result
            first_place = places[0]
            _safe_print(f"\n2. Getting details for: {first_place['name']}...")
            details = await collector.get_place_details(first_place["id"])

            _safe_print(f"   Name: {details['name']}")
            _safe_print(f"   Address: {details['address']}")
            _safe_print(f"   Rating: {details['rating']} ({details['user_rating_count']} reviews)")
            _safe_print(f"   Price Level: {details['price_range'] or 'N/A'}")
            _safe_print(f"   Phone: {details['phone'] or 'N/A'}")
            _safe_print(f"   Website: {details['website'] or 'N/A'}")
            _safe_print(f"   Type: {details['primary_type']}")

            if details.get("opening_hours"):
                _safe_print("   Hours:")
                for day in details["opening_hours"].get("weekday_text", [])[:3]:
                    _safe_print(f"      {day}")

            # 3. Get reviews
            _safe_print(f"\n3. Getting reviews for: {first_place['name']}...")
            reviews = await collector.get_place_reviews(first_place["id"])

            _safe_print(f"   Found {len(reviews)} reviews:")
            for review in reviews[:3]:
                _safe_print(f"\n   - {review['author_name']} ({review['rating']}/5)")
                text = review["text"][:150] + "..." if len(review["text"]) > 150 else review["text"]
                _safe_print(f"     \"{text}\"")

            # 4. Find nearby competitors
            _safe_print("\n4. Finding nearby competitors...")
            competitors = await collector.find_nearby_competitors(
                first_place["id"],
                radius_meters=1000
            )

            _safe_print(f"   Found {len(competitors)} competitors within 1km:")
            for i, comp in enumerate(competitors[:5], 1):
                _safe_print(f"   {i}. {comp['name']}")
                _safe_print(f"      {comp['address']}")

            # 5. Convert to Pydantic models
            _safe_print("\n5. Converting to Pydantic models...")
            business = collector.to_business_model(details, is_client=True)
            _safe_print(f"   Business: {business.name}")
            _safe_print(f"   ID: {business.id}")
            _safe_print(f"   Google Place ID: {business.google_place_id}")

            if reviews:
                review_model = collector.to_review_model(reviews[0], str(business.id))
                _safe_print(f"\n   Review: {review_model.author_name}")
                _safe_print(f"   Rating: {review_model.rating}")
                _safe_print(f"   Platform: {review_model.platform.value}")

            _safe_print("\n" + "=" * 60)
            _safe_print("Test completed successfully!")
            _safe_print("=" * 60)

    except GooglePlacesAuthError as e:
        _safe_print(f"\nAuthentication Error: {e}")
        _safe_print("Please check your GOOGLE_PLACES_API_KEY in .env")
    except GooglePlacesError as e:
        _safe_print(f"\nAPI Error: {e}")
    except Exception as e:
        _safe_print(f"\nUnexpected Error: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_google_places())
