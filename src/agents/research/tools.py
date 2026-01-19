"""Research tools for competitive intelligence data collection.

All tools return JSON-formatted strings with provenance fields
for downstream agent compatibility (especially Analyst Agent).
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool


def _json_response(data: Dict[str, Any], source: str) -> str:
    """Format response as JSON with provenance."""
    data["source"] = source
    data["collected_at"] = datetime.now(timezone.utc).isoformat()
    return json.dumps(data, indent=2, default=str)


def _error_response(error: str, source: str) -> str:
    """Format error response as JSON."""
    return json.dumps({
        "error": error,
        "source": source,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    })


@tool
async def collect_business_data(
    query: str,
    location: str = "",
    limit: int = 20,
) -> str:
    """Collect business data from Google Places and other sources.

    Args:
        query: Search query (e.g., "coffee shops", "Italian restaurants")
        location: Geographic location (e.g., "Austin, TX")
        limit: Maximum number of results to return

    Returns:
        JSON string with business data and provenance fields.
    """
    try:
        from src.collectors.registry import get_collector, CollectorType

        # Try to use Google Places collector
        try:
            collector = get_collector(
                CollectorType.GOOGLE_PLACES,
                {"query": query, "location": location}
            )
            results = []
            async for item in collector.collect():
                results.append(item)
                if len(results) >= limit:
                    break

            return _json_response({
                "businesses": results,
                "count": len(results),
                "query": query,
                "location": location,
            }, "google_places")

        except (ValueError, ImportError):
            # Collector not available, return empty result
            return _json_response({
                "businesses": [],
                "count": 0,
                "query": query,
                "location": location,
                "note": "Google Places collector not available",
            }, "google_places")

    except Exception as e:
        return _error_response(str(e), "collect_business_data")


@tool
async def search_competitors(
    query: str,
    location: str = "",
    limit: int = 10,
) -> str:
    """Search for competitor businesses in a market.

    Args:
        query: Business type or name to find competitors for
        location: Geographic area to search
        limit: Maximum competitors to return

    Returns:
        JSON string with competitor data and analysis.
    """
    try:
        from src.collectors.registry import get_collector, CollectorType

        try:
            collector = get_collector(
                CollectorType.GOOGLE_PLACES,
                {"query": query, "location": location}
            )
            competitors = []
            async for item in collector.collect():
                competitors.append({
                    "name": item.get("name", "Unknown"),
                    "rating": item.get("rating"),
                    "rating_count": item.get("rating_count", 0),
                    "address": item.get("address", ""),
                    "place_id": item.get("place_id", ""),
                })
                if len(competitors) >= limit:
                    break

            return _json_response({
                "competitors": competitors,
                "count": len(competitors),
                "query": query,
                "location": location,
            }, "competitor_search")

        except (ValueError, ImportError):
            return _json_response({
                "competitors": [],
                "count": 0,
                "query": query,
                "location": location,
                "note": "Competitor search not available",
            }, "competitor_search")

    except Exception as e:
        return _error_response(str(e), "search_competitors")


@tool
async def analyze_market(
    query: str,
    location: str = "",
) -> str:
    """Analyze market trends and opportunities.

    Args:
        query: Market or industry to analyze
        location: Geographic market area

    Returns:
        JSON string with market analysis data.
    """
    try:
        # This would integrate with knowledge store for market data
        # For now, return placeholder structure
        return _json_response({
            "market": query,
            "location": location,
            "trends": [],
            "opportunities": [],
            "threats": [],
            "note": "Full market analysis requires knowledge store integration",
        }, "market_analysis")

    except Exception as e:
        return _error_response(str(e), "analyze_market")


@tool
async def monitor_social(
    query: str,
    platforms: List[str] = None,
    limit: int = 50,
) -> str:
    """Monitor social media for mentions and sentiment.

    Args:
        query: Keywords or business name to monitor
        platforms: Social platforms to check (twitter, instagram)
        limit: Maximum posts to collect

    Returns:
        JSON string with social media data.
    """
    if platforms is None:
        platforms = ["twitter", "instagram"]

    try:
        from src.collectors.registry import get_collector, CollectorType

        all_posts = []

        for platform in platforms:
            try:
                if platform == "twitter":
                    collector_type = CollectorType.TWITTER
                elif platform == "instagram":
                    collector_type = CollectorType.INSTAGRAM
                else:
                    continue

                collector = get_collector(collector_type, {"query": query})
                async for post in collector.collect():
                    all_posts.append({
                        "platform": platform,
                        "content": post.get("content", ""),
                        "author": post.get("author", ""),
                        "engagement": post.get("engagement", 0),
                    })
                    if len(all_posts) >= limit:
                        break

            except (ValueError, ImportError):
                continue  # Skip unavailable collectors

        return _json_response({
            "posts": all_posts,
            "count": len(all_posts),
            "query": query,
            "platforms": platforms,
        }, "social_monitoring")

    except Exception as e:
        return _error_response(str(e), "monitor_social")
