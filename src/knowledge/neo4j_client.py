"""
Neo4j Knowledge Graph Client.

Provides async connection management and query execution for the LocalPulse
knowledge graph. Implements the context manager pattern for safe resource handling.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable, AuthError, Neo4jError

from src.config import settings
from src.core.circuit_breaker import get_circuit_breaker
from src.core.exceptions import (
    KnowledgeStoreConnectionError,
    KnowledgeStoreError,
    KnowledgeStoreQueryError,
)

logger = structlog.get_logger(__name__)

# Circuit breaker for Neo4j operations
_neo4j_breaker = get_circuit_breaker("neo4j", failure_threshold=5, recovery_timeout=60)


class Neo4jClient:
    """
    Async Neo4j client with connection management.

    Usage:
        async with Neo4jClient() as client:
            result = await client.run_query("MATCH (n) RETURN n LIMIT 10")
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        """
        Initialize the Neo4j client.

        Args:
            uri: Neo4j connection URI. Defaults to settings.neo4j_uri.
            user: Neo4j username. Defaults to settings.neo4j_user.
            password: Neo4j password. Defaults to settings.neo4j_password.
        """
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password.get_secret_value()
        self._driver: AsyncDriver | None = None

    async def connect(self, auto_init_schema: bool = True) -> None:
        """Establish connection to Neo4j database.

        Args:
            auto_init_schema: Initialize schema (constraints/indexes) on first connect.

        Raises:
            KnowledgeStoreConnectionError: If connection fails.
        """
        if self._driver is not None:
            return

        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            logger.info("neo4j_connected", uri=self._uri)

            # Auto-initialize schema on first connect
            if auto_init_schema:
                await self._initialize_schema()

        except AuthError as e:
            logger.error("neo4j_auth_failed", error=str(e), uri=self._uri)
            raise KnowledgeStoreConnectionError(
                f"Neo4j authentication failed: {e}",
                {"uri": self._uri, "original_error": str(e)},
            )
        except ServiceUnavailable as e:
            logger.error("neo4j_unavailable", error=str(e), uri=self._uri)
            raise KnowledgeStoreConnectionError(
                f"Neo4j service unavailable: {e}",
                {"uri": self._uri, "original_error": str(e)},
            )
        except KnowledgeStoreConnectionError:
            raise
        except Exception as e:
            logger.error(
                "neo4j_connection_failed",
                error=str(e),
                error_type=type(e).__name__,
                uri=self._uri,
            )
            raise KnowledgeStoreConnectionError(
                f"Failed to connect to Neo4j: {e}",
                {"uri": self._uri, "original_error": str(e)},
            )

    async def _initialize_schema(self) -> None:
        """Initialize schema with constraints and indexes.

        Creates the required schema if not already present.
        Safe to call multiple times - constraints use IF NOT EXISTS.
        """
        logger.info("neo4j_schema_auto_init_starting")

        statements = [
            stmt.strip()
            for stmt in SCHEMA_CONSTRAINTS.strip().split(";")
            if stmt.strip() and not stmt.strip().startswith("//")
        ]

        initialized_count = 0
        for statement in statements:
            if statement:
                try:
                    # Use direct session to avoid circuit breaker during init
                    async with self._driver.session(database="neo4j") as session:
                        await session.run(statement)
                    initialized_count += 1
                except Exception as e:
                    # Constraints may already exist, log and continue
                    logger.debug(
                        "neo4j_schema_item_skipped",
                        statement=statement[:50],
                        reason=str(e),
                    )

        logger.info(
            "neo4j_schema_auto_init_complete",
            total_statements=len(statements),
            initialized=initialized_count,
        )

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("neo4j_disconnected")

    async def __aenter__(self) -> Neo4jClient:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def driver(self) -> AsyncDriver:
        """Get the Neo4j driver, raising if not connected."""
        if self._driver is None:
            raise RuntimeError("Neo4j client not connected. Use 'async with' or call connect().")
        return self._driver

    async def run_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        """
        Execute a Cypher query and return results.

        Args:
            query: Cypher query string.
            parameters: Query parameters.
            database: Target database name.

        Returns:
            List of records as dictionaries.

        Raises:
            KnowledgeStoreError: If circuit breaker is open.
            KnowledgeStoreQueryError: If query fails.
        """
        # Check circuit breaker
        if not _neo4j_breaker.can_execute():
            recovery_time = _neo4j_breaker.time_until_recovery()
            logger.warning("neo4j_circuit_open", recovery_time=recovery_time)
            raise KnowledgeStoreError(
                f"Neo4j circuit breaker open. Recovery in {recovery_time:.1f}s",
                {"recovery_time": recovery_time},
            )

        try:
            async with self.driver.session(database=database) as session:
                result = await session.run(query, parameters or {})
                records = await result.data()
                await _neo4j_breaker.record_success()
                logger.debug("neo4j_query_executed", query=query[:100], record_count=len(records))
                return records

        except ServiceUnavailable as e:
            await _neo4j_breaker.record_failure()
            logger.error("neo4j_service_unavailable", query=query[:100], error=str(e))
            raise KnowledgeStoreQueryError(
                f"Neo4j service unavailable: {e}",
                {"query": query[:100], "original_error": str(e)},
            )
        except Neo4jError as e:
            await _neo4j_breaker.record_failure()
            logger.error(
                "neo4j_query_failed",
                query=query[:100],
                error=str(e),
                error_type=type(e).__name__,
            )
            raise KnowledgeStoreQueryError(
                f"Neo4j query failed: {e}",
                {"query": query[:100], "original_error": str(e)},
            )
        except Exception as e:
            await _neo4j_breaker.record_failure()
            logger.error(
                "neo4j_query_error",
                query=query[:100],
                error=str(e),
                error_type=type(e).__name__,
            )
            raise KnowledgeStoreQueryError(
                f"Failed to execute Neo4j query: {e}",
                {"query": query[:100], "original_error": str(e)},
            )

    async def run_write_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        """
        Execute a write transaction.

        Args:
            query: Cypher query string.
            parameters: Query parameters.
            database: Target database name.

        Returns:
            List of records as dictionaries.

        Raises:
            KnowledgeStoreError: If circuit breaker is open.
            KnowledgeStoreQueryError: If query fails.
        """
        # Check circuit breaker
        if not _neo4j_breaker.can_execute():
            recovery_time = _neo4j_breaker.time_until_recovery()
            logger.warning("neo4j_circuit_open", recovery_time=recovery_time)
            raise KnowledgeStoreError(
                f"Neo4j circuit breaker open. Recovery in {recovery_time:.1f}s",
                {"recovery_time": recovery_time},
            )

        async def _write_tx(tx: AsyncSession) -> list[dict[str, Any]]:
            result = await tx.run(query, parameters or {})
            return await result.data()

        try:
            async with self.driver.session(database=database) as session:
                records = await session.execute_write(lambda tx: _write_tx(tx))
                await _neo4j_breaker.record_success()
                logger.debug("neo4j_write_executed", query=query[:100], record_count=len(records))
                return records

        except ServiceUnavailable as e:
            await _neo4j_breaker.record_failure()
            logger.error("neo4j_write_unavailable", query=query[:100], error=str(e))
            raise KnowledgeStoreQueryError(
                f"Neo4j service unavailable during write: {e}",
                {"query": query[:100], "original_error": str(e)},
            )
        except Neo4jError as e:
            await _neo4j_breaker.record_failure()
            logger.error(
                "neo4j_write_failed",
                query=query[:100],
                error=str(e),
                error_type=type(e).__name__,
            )
            raise KnowledgeStoreQueryError(
                f"Neo4j write query failed: {e}",
                {"query": query[:100], "original_error": str(e)},
            )
        except Exception as e:
            await _neo4j_breaker.record_failure()
            logger.error(
                "neo4j_write_error",
                query=query[:100],
                error=str(e),
                error_type=type(e).__name__,
            )
            raise KnowledgeStoreQueryError(
                f"Failed to execute Neo4j write: {e}",
                {"query": query[:100], "original_error": str(e)},
            )


# =============================================================================
# Schema Initialization
# =============================================================================

SCHEMA_CONSTRAINTS = """
// Business node constraints and indexes
CREATE CONSTRAINT business_id IF NOT EXISTS FOR (b:Business) REQUIRE b.id IS UNIQUE;
CREATE CONSTRAINT business_google_place_id IF NOT EXISTS FOR (b:Business) REQUIRE b.google_place_id IS UNIQUE;
CREATE INDEX business_name IF NOT EXISTS FOR (b:Business) ON (b.name);
CREATE INDEX business_cuisine IF NOT EXISTS FOR (b:Business) ON (b.cuisine_type);

// Review node constraints and indexes
CREATE CONSTRAINT review_id IF NOT EXISTS FOR (r:Review) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT review_google_id IF NOT EXISTS FOR (r:Review) REQUIRE r.google_review_id IS UNIQUE;
CREATE INDEX review_rating IF NOT EXISTS FOR (r:Review) ON (r.rating);
CREATE INDEX review_date IF NOT EXISTS FOR (r:Review) ON (r.date);

// Competitor node constraints and indexes
CREATE CONSTRAINT competitor_id IF NOT EXISTS FOR (c:Competitor) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT competitor_google_place_id IF NOT EXISTS FOR (c:Competitor) REQUIRE c.google_place_id IS UNIQUE;

// Location node constraints and indexes
CREATE CONSTRAINT location_id IF NOT EXISTS FOR (l:Location) REQUIRE l.id IS UNIQUE;
CREATE INDEX location_city IF NOT EXISTS FOR (l:Location) ON (l.city);
CREATE INDEX location_area IF NOT EXISTS FOR (l:Location) ON (l.area);

// Event node constraints and indexes
CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE;
CREATE INDEX event_date IF NOT EXISTS FOR (e:Event) ON (e.date);
CREATE INDEX event_type IF NOT EXISTS FOR (e:Event) ON (e.event_type);

// Theme node constraints and indexes
CREATE CONSTRAINT theme_id IF NOT EXISTS FOR (t:Theme) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT theme_name IF NOT EXISTS FOR (t:Theme) REQUIRE t.name IS UNIQUE;
"""


async def initialize_schema(client: Neo4jClient) -> None:
    """
    Initialize the knowledge graph schema with constraints and indexes.

    Creates:
        Node types: Business, Review, Competitor, Location, Event, Theme
        Relationships: LOCATED_IN, HAS_REVIEW, COMPETES_WITH, MENTIONS_THEME, AFFECTS

    Args:
        client: Connected Neo4jClient instance.
    """
    logger.info("neo4j_schema_init_started")

    # Split constraints into individual statements and execute
    statements = [
        stmt.strip()
        for stmt in SCHEMA_CONSTRAINTS.strip().split(";")
        if stmt.strip() and not stmt.strip().startswith("//")
    ]

    for statement in statements:
        if statement:
            try:
                await client.run_query(statement)
                logger.debug("neo4j_constraint_created", statement=statement[:50])
            except Exception as e:
                # Constraints may already exist, log and continue
                logger.warning("neo4j_constraint_skipped", statement=statement[:50], reason=str(e))

    logger.info("neo4j_schema_init_completed", constraint_count=len(statements))


async def create_sample_business(client: Neo4jClient) -> dict[str, Any]:
    """
    Create a sample business node for testing.

    Args:
        client: Connected Neo4jClient instance.

    Returns:
        Created business node data.
    """
    query = """
    MERGE (b:Business {id: $id})
    SET b.name = $name,
        b.google_place_id = $google_place_id,
        b.cuisine_type = $cuisine_type,
        b.price_range = $price_range,
        b.avg_rating = $avg_rating,
        b.address = $address,
        b.phone = $phone,
        b.website = $website,
        b.created_at = $created_at,
        b.updated_at = $updated_at
    RETURN b
    """

    now = datetime.utcnow().isoformat()
    parameters = {
        "id": "sample_business_001",
        "name": "Sample Italian Restaurant",
        "google_place_id": "ChIJ_sample_place_id",
        "cuisine_type": "Italian",
        "price_range": "$$",
        "avg_rating": 4.5,
        "address": "123 Main Street, San Francisco, CA 94102",
        "phone": "+1-415-555-0100",
        "website": "https://sample-restaurant.com",
        "created_at": now,
        "updated_at": now,
    }

    result = await client.run_query(query, parameters)
    logger.info("neo4j_sample_business_created", business_id=parameters["id"])
    return result[0] if result else {}


async def create_sample_location(client: Neo4jClient, business_id: str) -> dict[str, Any]:
    """
    Create a sample location and link it to a business.

    Args:
        client: Connected Neo4jClient instance.
        business_id: ID of the business to link.

    Returns:
        Created relationship data.
    """
    query = """
    MERGE (l:Location {id: $location_id})
    SET l.city = $city,
        l.area = $area,
        l.postcode = $postcode,
        l.lat = $lat,
        l.lng = $lng
    WITH l
    MATCH (b:Business {id: $business_id})
    MERGE (b)-[r:LOCATED_IN]->(l)
    RETURN b.name AS business, l.city AS city, l.area AS area
    """

    parameters = {
        "location_id": "loc_sf_downtown",
        "city": "San Francisco",
        "area": "Downtown",
        "postcode": "94102",
        "lat": 37.7749,
        "lng": -122.4194,
        "business_id": business_id,
    }

    result = await client.run_query(query, parameters)
    logger.info("neo4j_sample_location_created", location_id=parameters["location_id"])
    return result[0] if result else {}


# =============================================================================
# Test Function
# =============================================================================

async def test_connection() -> None:
    """
    Test Neo4j connection and create sample data.

    This function:
    1. Connects to Neo4j using credentials from settings
    2. Initializes the schema (constraints and indexes)
    3. Creates a sample business node
    4. Creates a sample location and links it to the business
    5. Queries and displays the created data
    """
    print("=" * 60)
    print("Neo4j Connection Test")
    print("=" * 60)

    async with Neo4jClient() as client:
        print(f"\n[OK] Connected to: {settings.neo4j_uri}")

        # Initialize schema
        print("\nInitializing schema...")
        await initialize_schema(client)
        print("[OK] Schema initialized")

        # Create sample business
        print("\nCreating sample business...")
        business = await create_sample_business(client)
        print(f"[OK] Created business: {business}")

        # Create location and link
        print("\nCreating location and relationship...")
        location = await create_sample_location(client, "sample_business_001")
        print(f"[OK] Created relationship: {location}")

        # Query to verify
        print("\nVerifying data...")
        verify_query = """
        MATCH (b:Business)-[:LOCATED_IN]->(l:Location)
        RETURN b.name AS business, b.cuisine_type AS cuisine,
               l.city AS city, l.area AS area
        LIMIT 5
        """
        results = await client.run_query(verify_query)
        print("[OK] Query results:")
        for record in results:
            print(f"  - {record['business']} ({record['cuisine']}) in {record['city']}, {record['area']}")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_connection())
