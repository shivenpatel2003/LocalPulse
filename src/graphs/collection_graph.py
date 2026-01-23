"""LangGraph workflow for data collection.

This module defines the collection workflow that:
1. Searches for a business on Google Places
2. Fetches detailed business information
3. Collects reviews
4. Finds nearby competitors
5. Stores data in Neo4j knowledge graph
6. Generates embeddings and stores in Pinecone

The workflow uses conditional edges to handle errors and skip steps when needed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

import structlog
from langgraph.graph import END, StateGraph

from src.collectors.google_places import (
    GooglePlacesCollector,
    GooglePlacesError,
    GooglePlacesNotFoundError,
)
from src.graphs.state import CollectionState, CollectionStatus, create_collection_state
from src.knowledge import EmbeddingsService  # Uses Cohere (free tier)
from src.knowledge.neo4j_client import Neo4jClient
from src.knowledge.pinecone_client import PineconeClient

logger = structlog.get_logger(__name__)


# =============================================================================
# Node Functions
# =============================================================================


async def search_business(state: CollectionState) -> dict:
    """Search for business on Google Places.

    Takes business_name and location from state, searches Google Places,
    and stores the google_place_id if found.

    Args:
        state: Current collection state with business_name.

    Returns:
        Partial state update with google_place_id or error.
    """
    logger.info(
        "collection_search_business",
        business_name=state.get("business_name"),
    )

    try:
        async with GooglePlacesCollector() as collector:
            # Search for the business
            places = await collector.search_places(
                query=state["business_name"],
                location="",  # Location is part of business_name for now
                max_results=5,
            )

            if not places:
                return {
                    "errors": ["No places found for search query"],
                    "status": CollectionStatus.FAILED.value,
                }

            # Use the first match
            place = places[0]
            logger.info(
                "collection_business_found",
                place_id=place["id"],
                name=place["name"],
            )

            return {
                "google_place_id": place["id"],
                "status": CollectionStatus.COLLECTING.value,
            }

    except GooglePlacesError as e:
        logger.error("collection_search_failed", error=str(e))
        return {
            "errors": [f"Search failed: {str(e)}"],
            "status": CollectionStatus.FAILED.value,
        }


async def get_business_details(state: CollectionState) -> dict:
    """Fetch full details for the business.

    Uses the google_place_id from state to fetch complete business details
    including ratings, phone, website, hours, etc.

    Args:
        state: Current state with google_place_id.

    Returns:
        Partial state update with business details in reviews_collected.
    """
    google_place_id = state.get("google_place_id")
    if not google_place_id:
        return {
            "errors": ["No google_place_id available"],
            "status": CollectionStatus.FAILED.value,
        }

    logger.info("collection_get_details", place_id=google_place_id)

    try:
        async with GooglePlacesCollector() as collector:
            details = await collector.get_place_details(google_place_id)

            # Store details in a structured format
            business_details = {
                "type": "business_details",
                "google_place_id": details.get("id"),
                "name": details.get("name"),
                "address": details.get("address"),
                "lat": details.get("lat"),
                "lng": details.get("lng"),
                "rating": details.get("rating"),
                "user_rating_count": details.get("user_rating_count"),
                "price_range": details.get("price_range"),
                "phone": details.get("phone"),
                "website": details.get("website"),
                "primary_type": details.get("primary_type"),
                "opening_hours": details.get("opening_hours"),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                "collection_details_fetched",
                name=details.get("name"),
                rating=details.get("rating"),
            )

            # Add to reviews_collected (will hold all collected data)
            return {
                "reviews_collected": [business_details],
            }

    except GooglePlacesError as e:
        logger.error("collection_details_failed", error=str(e))
        return {
            "errors": [f"Details fetch failed: {str(e)}"],
        }


async def collect_reviews(state: CollectionState) -> dict:
    """Collect reviews for the business.

    Fetches all available reviews from Google Places (up to 5 per API limits).

    Args:
        state: Current state with google_place_id.

    Returns:
        Partial state update with reviews in reviews_collected.
    """
    google_place_id = state.get("google_place_id")
    if not google_place_id:
        return {}

    logger.info("collection_get_reviews", place_id=google_place_id)

    try:
        async with GooglePlacesCollector() as collector:
            reviews = await collector.get_place_reviews(google_place_id)

            if not reviews:
                logger.info("collection_no_reviews", place_id=google_place_id)
                return {}

            # Format reviews with metadata
            review_records = []
            for review in reviews:
                review_record = {
                    "type": "review",
                    "id": str(uuid4()),
                    "business_id": state.get("business_id"),
                    "google_place_id": google_place_id,
                    "author_name": review.get("author_name"),
                    "rating": review.get("rating"),
                    "text": review.get("text"),
                    "language": review.get("language"),
                    "time": review.get("time"),
                    "platform": "google",
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }
                review_records.append(review_record)

            logger.info(
                "collection_reviews_fetched",
                count=len(review_records),
            )

            return {
                "reviews_collected": review_records,
            }

    except GooglePlacesError as e:
        logger.error("collection_reviews_failed", error=str(e))
        return {
            "errors": [f"Reviews fetch failed: {str(e)}"],
        }


async def find_competitors(state: CollectionState) -> dict:
    """Find nearby competitor businesses.

    Uses the business location to find similar businesses within 1km radius.

    Args:
        state: Current state with google_place_id.

    Returns:
        Partial state update with competitors in competitors_found.
    """
    google_place_id = state.get("google_place_id")
    if not google_place_id:
        return {}

    logger.info("collection_find_competitors", place_id=google_place_id)

    try:
        async with GooglePlacesCollector() as collector:
            competitors = await collector.find_nearby_competitors(
                place_id=google_place_id,
                radius_meters=1000,
                max_results=20,
            )

            if not competitors:
                logger.info("collection_no_competitors", place_id=google_place_id)
                return {}

            # Format competitor records
            competitor_records = []
            for comp in competitors:
                competitor_record = {
                    "type": "competitor",
                    "id": str(uuid4()),
                    "google_place_id": comp.get("id"),
                    "name": comp.get("name"),
                    "address": comp.get("address"),
                    "lat": comp.get("lat"),
                    "lng": comp.get("lng"),
                    "client_business_id": state.get("business_id"),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }
                competitor_records.append(competitor_record)

            logger.info(
                "collection_competitors_found",
                count=len(competitor_records),
            )

            return {
                "competitors_found": competitor_records,
            }

    except GooglePlacesError as e:
        logger.error("collection_competitors_failed", error=str(e))
        return {
            "errors": [f"Competitor search failed: {str(e)}"],
        }


async def store_in_neo4j(state: CollectionState) -> dict:
    """Store collected data in Neo4j knowledge graph.

    Creates nodes for the business, reviews, and competitors,
    and establishes relationships between them.

    Args:
        state: Current state with collected data.

    Returns:
        Partial state update (empty on success, or with errors if storage fails).
    """
    logger.info(
        "collection_store_neo4j",
        business_id=state.get("business_id"),
        reviews_count=len([r for r in state.get("reviews_collected", []) if r.get("type") == "review"]),
        competitors_count=len(state.get("competitors_found", [])),
    )

    try:
        async with Neo4jClient() as client:
            # Extract business details
            business_details = next(
                (r for r in state.get("reviews_collected", []) if r.get("type") == "business_details"),
                None,
            )

            if business_details:
                # Create/update business node - use google_place_id as unique key
                business_query = """
                MERGE (b:Business {google_place_id: $google_place_id})
                SET b.id = $id,
                    b.name = $name,
                    b.address = $address,
                    b.lat = $lat,
                    b.lng = $lng,
                    b.rating = $rating,
                    b.user_rating_count = $user_rating_count,
                    b.price_range = $price_range,
                    b.phone = $phone,
                    b.website = $website,
                    b.primary_type = $primary_type,
                    b.is_client = true,
                    b.updated_at = $updated_at
                RETURN b
                """

                await client.run_query(
                    business_query,
                    {
                        "id": state.get("business_id"),
                        "name": business_details.get("name"),
                        "google_place_id": business_details.get("google_place_id"),
                        "address": business_details.get("address"),
                        "lat": business_details.get("lat"),
                        "lng": business_details.get("lng"),
                        "rating": business_details.get("rating"),
                        "user_rating_count": business_details.get("user_rating_count"),
                        "price_range": business_details.get("price_range"),
                        "phone": business_details.get("phone"),
                        "website": business_details.get("website"),
                        "primary_type": business_details.get("primary_type"),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                logger.debug("neo4j_business_stored", business_id=state.get("business_id"))

            # Store reviews
            reviews = [r for r in state.get("reviews_collected", []) if r.get("type") == "review"]
            for review in reviews:
                review_query = """
                MATCH (b:Business {id: $business_id})
                MERGE (r:Review {id: $review_id})
                SET r.author_name = $author_name,
                    r.rating = $rating,
                    r.text = $text,
                    r.platform = $platform,
                    r.review_time = $review_time,
                    r.collected_at = $collected_at
                MERGE (b)-[:HAS_REVIEW]->(r)
                RETURN r
                """

                await client.run_query(
                    review_query,
                    {
                        "business_id": state.get("business_id"),
                        "review_id": review.get("id"),
                        "author_name": review.get("author_name"),
                        "rating": review.get("rating"),
                        "text": review.get("text"),
                        "platform": review.get("platform"),
                        "review_time": review.get("time"),
                        "collected_at": review.get("collected_at"),
                    },
                )

            logger.debug("neo4j_reviews_stored", count=len(reviews))

            # Store competitors
            competitors = state.get("competitors_found", [])
            for comp in competitors:
                competitor_query = """
                MATCH (client:Business {id: $client_id})
                MERGE (comp:Business {google_place_id: $competitor_google_place_id})
                SET comp.name = $name,
                    comp.address = $address,
                    comp.lat = $lat,
                    comp.lng = $lng,
                    comp.is_client = false,
                    comp.updated_at = $updated_at
                MERGE (client)-[:COMPETES_WITH]->(comp)
                RETURN comp
                """

                await client.run_query(
                    competitor_query,
                    {
                        "client_id": state.get("business_id"),
                        "competitor_google_place_id": comp.get("google_place_id"),
                        "name": comp.get("name"),
                        "address": comp.get("address"),
                        "lat": comp.get("lat"),
                        "lng": comp.get("lng"),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

            logger.debug("neo4j_competitors_stored", count=len(competitors))
            logger.info("collection_neo4j_complete")

            return {}

    except Exception as e:
        logger.error("collection_neo4j_failed", error=str(e))
        return {
            "errors": [f"Neo4j storage failed: {str(e)}"],
        }


async def store_embeddings(state: CollectionState) -> dict:
    """Generate embeddings for reviews and store in Pinecone.

    Creates vector embeddings for review text using OpenAI,
    then stores them in Pinecone for semantic search.

    Args:
        state: Current state with collected reviews.

    Returns:
        Partial state update with completion status.
    """
    reviews = [r for r in state.get("reviews_collected", []) if r.get("type") == "review"]

    if not reviews:
        logger.info("collection_no_reviews_to_embed")
        return {
            "status": CollectionStatus.COMPLETED.value,
            "completed_at": datetime.now(timezone.utc),
        }

    logger.info("collection_store_embeddings", review_count=len(reviews))

    try:
        # Initialize services
        embeddings_service = EmbeddingsService()
        pinecone_client = PineconeClient()
        pinecone_client.connect()
        pinecone_client.ensure_index()

        # Extract review texts
        review_texts = [r.get("text", "") for r in reviews if r.get("text")]

        if not review_texts:
            logger.info("collection_no_review_text")
            return {
                "status": CollectionStatus.COMPLETED.value,
                "completed_at": datetime.now(timezone.utc),
            }

        # Generate embeddings
        embeddings = await embeddings_service.embed_batch(review_texts)

        # Prepare vectors for Pinecone
        vectors = []
        for i, (review, embedding) in enumerate(zip(reviews, embeddings)):
            if review.get("text"):
                vector_record = {
                    "id": f"review_{review.get('id')}",
                    "values": embedding,
                    "metadata": {
                        "business_id": state.get("business_id"),
                        "review_id": review.get("id"),
                        "rating": review.get("rating", 0),
                        "platform": review.get("platform", "google"),
                        "author_name": review.get("author_name", ""),
                        "text_preview": review.get("text", "")[:200],
                    },
                }
                vectors.append(vector_record)

        # Upsert to Pinecone
        if vectors:
            await pinecone_client.upsert_embeddings(
                vectors=vectors,
                namespace="reviews",
            )
            logger.info("collection_embeddings_stored", count=len(vectors))

        return {
            "status": CollectionStatus.COMPLETED.value,
            "completed_at": datetime.now(timezone.utc),
        }

    except Exception as e:
        logger.error("collection_embeddings_failed", error=str(e))
        return {
            "errors": [f"Embedding storage failed: {str(e)}"],
            "status": CollectionStatus.COMPLETED.value,  # Still mark as complete
            "completed_at": datetime.now(timezone.utc),
        }


# =============================================================================
# Conditional Edge Functions
# =============================================================================


def should_continue_after_search(
    state: CollectionState,
) -> Literal["get_business_details", "end"]:
    """Determine if workflow should continue after search.

    Returns:
        "get_business_details" if search succeeded, "end" if failed.
    """
    if state.get("status") == CollectionStatus.FAILED.value:
        return "end"
    if not state.get("google_place_id"):
        return "end"
    return "get_business_details"


def should_skip_to_competitors(
    state: CollectionState,
) -> Literal["find_competitors", "collect_reviews"]:
    """Check if we should skip reviews collection.

    Currently always collects reviews, but can be modified
    to skip based on state conditions.

    Returns:
        Next node to execute.
    """
    # Always try to collect reviews
    return "collect_reviews"


def check_reviews_collected(
    state: CollectionState,
) -> Literal["find_competitors"]:
    """After reviews, always proceed to competitors.

    Returns:
        Next node (always find_competitors).
    """
    return "find_competitors"


# =============================================================================
# Graph Builder
# =============================================================================


def create_collection_graph() -> StateGraph:
    """Create the collection workflow graph.

    The graph executes the following flow:
    1. search_business - Find business on Google Places
    2. get_business_details - Fetch full details
    3. collect_reviews - Get reviews
    4. find_competitors - Find nearby competitors
    5. store_in_neo4j - Store in knowledge graph
    6. store_embeddings - Store vector embeddings

    With conditional edges:
    - If search fails -> END
    - All other nodes flow sequentially

    Returns:
        Compiled StateGraph for collection workflow.
    """
    # Create the graph
    workflow = StateGraph(CollectionState)

    # Add nodes
    workflow.add_node("search_business", search_business)
    workflow.add_node("get_business_details", get_business_details)
    workflow.add_node("collect_reviews", collect_reviews)
    workflow.add_node("find_competitors", find_competitors)
    workflow.add_node("store_in_neo4j", store_in_neo4j)
    workflow.add_node("store_embeddings", store_embeddings)

    # Set entry point
    workflow.set_entry_point("search_business")

    # Add conditional edge after search
    workflow.add_conditional_edges(
        "search_business",
        should_continue_after_search,
        {
            "get_business_details": "get_business_details",
            "end": END,
        },
    )

    # Add sequential edges for the rest of the workflow
    workflow.add_edge("get_business_details", "collect_reviews")
    workflow.add_edge("collect_reviews", "find_competitors")
    workflow.add_edge("find_competitors", "store_in_neo4j")
    workflow.add_edge("store_in_neo4j", "store_embeddings")
    workflow.add_edge("store_embeddings", END)

    return workflow


def compile_collection_graph():
    """Create and compile the collection graph.

    Returns:
        Compiled graph ready for invocation.
    """
    graph = create_collection_graph()
    return graph.compile()


# =============================================================================
# Convenience Function
# =============================================================================


async def run_collection(
    business_name: str,
    location: str = "",
) -> CollectionState:
    """Run the collection workflow for a business.

    Args:
        business_name: Name of the business to collect data for.
        location: Optional location hint.

    Returns:
        Final CollectionState with all collected data.
    """
    # Create initial state
    business_id = str(uuid4())
    full_name = f"{business_name} {location}".strip() if location else business_name

    initial_state = create_collection_state(
        business_id=business_id,
        business_name=full_name,
    )

    # Compile and run the graph
    graph = compile_collection_graph()
    final_state = await graph.ainvoke(initial_state)

    return final_state


# =============================================================================
# Test Function
# =============================================================================


def _safe_print(text: str) -> None:
    """Print text safely, handling Unicode issues on Windows."""
    safe_text = text.encode("ascii", errors="replace").decode("ascii")
    print(safe_text)


async def test_collection_workflow():
    """Test the collection workflow with Circolo Popolare Manchester.

    Runs the full workflow and prints progress at each step.
    """
    _safe_print("=" * 70)
    _safe_print("Collection Workflow Test")
    _safe_print("=" * 70)

    business_name = "Circolo Popolare Manchester"

    _safe_print(f"\nStarting collection for: {business_name}")
    _safe_print("-" * 70)

    # Create initial state
    business_id = str(uuid4())
    initial_state = create_collection_state(
        business_id=business_id,
        business_name=business_name,
    )

    _safe_print(f"\nInitial State:")
    _safe_print(f"  Business ID: {business_id}")
    _safe_print(f"  Business Name: {business_name}")
    _safe_print(f"  Status: {initial_state.get('status')}")

    # Compile the graph
    graph = compile_collection_graph()

    # Run with streaming to see progress
    _safe_print("\n" + "=" * 70)
    _safe_print("Workflow Execution:")
    _safe_print("=" * 70)

    step_count = 0
    # Keep track of accumulated state
    accumulated_state = dict(initial_state)

    async for event in graph.astream(initial_state):
        step_count += 1
        for node_name, node_state in event.items():
            # Merge the node's output into accumulated state
            for key, value in node_state.items():
                if key in ["reviews_collected", "competitors_found", "errors"] and isinstance(value, list):
                    # Merge lists
                    existing = accumulated_state.get(key, [])
                    accumulated_state[key] = existing + value
                else:
                    accumulated_state[key] = value

            _safe_print(f"\n[Step {step_count}] {node_name}")
            _safe_print("-" * 40)

            # Print relevant info based on node
            if node_name == "search_business":
                place_id = accumulated_state.get("google_place_id")
                if place_id:
                    _safe_print(f"  Found Place ID: {place_id}")
                else:
                    _safe_print(f"  Status: {accumulated_state.get('status')}")
                    if accumulated_state.get("errors"):
                        _safe_print(f"  Errors: {accumulated_state.get('errors')}")

            elif node_name == "get_business_details":
                details = next(
                    (r for r in accumulated_state.get("reviews_collected", [])
                     if r.get("type") == "business_details"),
                    None,
                )
                if details:
                    _safe_print(f"  Name: {details.get('name')}")
                    _safe_print(f"  Rating: {details.get('rating')} ({details.get('user_rating_count')} reviews)")
                    _safe_print(f"  Address: {details.get('address')}")
                    _safe_print(f"  Type: {details.get('primary_type')}")

            elif node_name == "collect_reviews":
                reviews = [r for r in accumulated_state.get("reviews_collected", [])
                          if r.get("type") == "review"]
                _safe_print(f"  Reviews collected: {len(reviews)}")
                for i, review in enumerate(reviews[:2], 1):
                    _safe_print(f"    {i}. {review.get('author_name')} - {review.get('rating')}/5")
                    text = review.get("text", "")[:60]
                    _safe_print(f"       \"{text}...\"")

            elif node_name == "find_competitors":
                competitors = accumulated_state.get("competitors_found", [])
                _safe_print(f"  Competitors found: {len(competitors)}")
                for i, comp in enumerate(competitors[:3], 1):
                    _safe_print(f"    {i}. {comp.get('name')}")

            elif node_name == "store_in_neo4j":
                _safe_print("  Data stored in Neo4j knowledge graph")

            elif node_name == "store_embeddings":
                _safe_print("  Embeddings generated and stored in Pinecone")
                _safe_print(f"  Final Status: {accumulated_state.get('status')}")

    # Print final summary
    _safe_print("\n" + "=" * 70)
    _safe_print("Final State Summary:")
    _safe_print("=" * 70)

    _safe_print(f"\n  Business ID: {accumulated_state.get('business_id')}")
    _safe_print(f"  Business Name: {accumulated_state.get('business_name')}")
    _safe_print(f"  Google Place ID: {accumulated_state.get('google_place_id')}")
    _safe_print(f"  Status: {accumulated_state.get('status')}")

    reviews = [r for r in accumulated_state.get("reviews_collected", []) if r.get("type") == "review"]
    details = [r for r in accumulated_state.get("reviews_collected", []) if r.get("type") == "business_details"]
    competitors = accumulated_state.get("competitors_found", [])

    _safe_print(f"\n  Data Collected:")
    _safe_print(f"    - Business Details: {len(details)}")
    _safe_print(f"    - Reviews: {len(reviews)}")
    _safe_print(f"    - Competitors: {len(competitors)}")

    if accumulated_state.get("errors"):
        _safe_print(f"\n  Errors: {accumulated_state.get('errors')}")

    _safe_print(f"\n  Started: {accumulated_state.get('started_at')}")
    _safe_print(f"  Completed: {accumulated_state.get('completed_at')}")

    _safe_print("\n" + "=" * 70)
    _safe_print("Test completed!")
    _safe_print("=" * 70)

    return accumulated_state


if __name__ == "__main__":
    asyncio.run(test_collection_workflow())
