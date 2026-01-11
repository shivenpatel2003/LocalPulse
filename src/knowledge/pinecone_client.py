"""
Pinecone Vector Store Client.

Provides connection management and vector operations for the LocalPulse
semantic search layer. Uses text-embedding-3-large (3072 dimensions).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TypedDict

import structlog
from pinecone import Pinecone, ServerlessSpec

from src.config import settings

logger = structlog.get_logger(__name__)


# =============================================================================
# Metadata Schema
# =============================================================================


class ReviewMetadata(TypedDict):
    """Metadata schema for review vectors."""

    business_id: str
    review_id: str
    rating: float
    date: str
    platform: str
    sentiment_score: float


class VectorRecord(TypedDict):
    """Vector record for upsert operations."""

    id: str
    values: list[float]
    metadata: dict[str, Any]


# =============================================================================
# Pinecone Client
# =============================================================================


class PineconeClient:
    """
    Pinecone vector store client.

    Usage:
        client = PineconeClient()
        client.connect()

        # Upsert vectors
        await client.upsert_embeddings([
            {"id": "vec1", "values": [...], "metadata": {...}}
        ])

        # Query
        results = await client.query(query_vector, top_k=10)

        # Delete
        await client.delete(["vec1"])
    """

    # Index configuration
    DIMENSION = 3072  # text-embedding-3-large
    METRIC = "cosine"
    CLOUD = "aws"
    REGION = "us-east-1"

    def __init__(
        self,
        api_key: str | None = None,
        index_name: str | None = None,
    ) -> None:
        """
        Initialize the Pinecone client.

        Args:
            api_key: Pinecone API key. Defaults to settings.pinecone_api_key.
            index_name: Index name. Defaults to settings.pinecone_index_name.
        """
        self._api_key = api_key or settings.pinecone_api_key.get_secret_value()
        self._index_name = index_name or settings.pinecone_index_name
        self._client: Pinecone | None = None
        self._index: Any = None

    def connect(self) -> None:
        """Initialize connection to Pinecone."""
        if self._client is not None:
            return

        self._client = Pinecone(api_key=self._api_key)
        logger.info("pinecone_client_initialized")

    @property
    def client(self) -> Pinecone:
        """Get the Pinecone client, raising if not connected."""
        if self._client is None:
            raise RuntimeError("Pinecone client not initialized. Call connect() first.")
        return self._client

    @property
    def index(self) -> Any:
        """Get the Pinecone index, raising if not connected."""
        if self._index is None:
            raise RuntimeError("Pinecone index not initialized. Call ensure_index() first.")
        return self._index

    def ensure_index(self, wait_for_ready: bool = True) -> None:
        """
        Create the index if it doesn't exist and connect to it.

        Args:
            wait_for_ready: Wait for index to be ready before returning.
        """
        existing_indexes = [idx.name for idx in self.client.list_indexes()]

        if self._index_name not in existing_indexes:
            logger.info(
                "pinecone_creating_index",
                index_name=self._index_name,
                dimension=self.DIMENSION,
                metric=self.METRIC,
            )

            self.client.create_index(
                name=self._index_name,
                dimension=self.DIMENSION,
                metric=self.METRIC,
                spec=ServerlessSpec(
                    cloud=self.CLOUD,
                    region=self.REGION,
                ),
            )

            if wait_for_ready:
                self._wait_for_index_ready()

            logger.info("pinecone_index_created", index_name=self._index_name)
        else:
            logger.info("pinecone_index_exists", index_name=self._index_name)

        # Connect to the index
        self._index = self.client.Index(self._index_name)
        logger.info("pinecone_index_connected", index_name=self._index_name)

    def _wait_for_index_ready(self, timeout: int = 300) -> None:
        """
        Wait for index to be ready.

        Args:
            timeout: Maximum seconds to wait.
        """
        start_time = time.time()
        while True:
            try:
                description = self.client.describe_index(self._index_name)
                if description.status.ready:
                    return
            except Exception:
                pass

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Index {self._index_name} not ready after {timeout}s")

            time.sleep(5)
            logger.debug("pinecone_waiting_for_index", index_name=self._index_name)

    async def upsert_embeddings(
        self,
        vectors: list[VectorRecord],
        namespace: str = "",
        batch_size: int = 100,
    ) -> dict[str, int]:
        """
        Upsert vectors to the index.

        Args:
            vectors: List of vector records with id, values, and metadata.
            namespace: Optional namespace for organization.
            batch_size: Number of vectors per batch.

        Returns:
            Upsert statistics.
        """
        total_upserted = 0

        # Process in batches
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]

            # Convert to Pinecone format
            pinecone_vectors = [
                {
                    "id": v["id"],
                    "values": v["values"],
                    "metadata": v.get("metadata", {}),
                }
                for v in batch
            ]

            # Run upsert in thread pool (Pinecone client is sync)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.index.upsert(vectors=pinecone_vectors, namespace=namespace),
            )

            total_upserted += result.upserted_count
            logger.debug(
                "pinecone_batch_upserted",
                batch_size=len(batch),
                total=total_upserted,
            )

        logger.info("pinecone_upsert_completed", total_upserted=total_upserted)
        return {"upserted_count": total_upserted}

    async def query(
        self,
        vector: list[float],
        top_k: int = 10,
        filter: dict[str, Any] | None = None,
        namespace: str = "",
        include_metadata: bool = True,
        include_values: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Query the index for similar vectors.

        Args:
            vector: Query vector.
            top_k: Number of results to return.
            filter: Metadata filter.
            namespace: Optional namespace.
            include_metadata: Include metadata in results.
            include_values: Include vector values in results.

        Returns:
            List of matching records with id, score, and optional metadata/values.
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.index.query(
                vector=vector,
                top_k=top_k,
                filter=filter,
                namespace=namespace,
                include_metadata=include_metadata,
                include_values=include_values,
            ),
        )

        matches = []
        for match in result.matches:
            record = {
                "id": match.id,
                "score": match.score,
            }
            if include_metadata and match.metadata:
                record["metadata"] = dict(match.metadata)
            if include_values and match.values:
                record["values"] = list(match.values)
            matches.append(record)

        logger.debug("pinecone_query_completed", top_k=top_k, matches=len(matches))
        return matches

    async def delete(
        self,
        ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        namespace: str = "",
        delete_all: bool = False,
    ) -> None:
        """
        Delete vectors from the index.

        Args:
            ids: List of vector IDs to delete.
            filter: Metadata filter for deletion.
            namespace: Optional namespace.
            delete_all: Delete all vectors in namespace.
        """
        loop = asyncio.get_event_loop()

        if delete_all:
            await loop.run_in_executor(
                None,
                lambda: self.index.delete(delete_all=True, namespace=namespace),
            )
            logger.info("pinecone_delete_all", namespace=namespace)
        elif ids:
            await loop.run_in_executor(
                None,
                lambda: self.index.delete(ids=ids, namespace=namespace),
            )
            logger.info("pinecone_delete_ids", count=len(ids))
        elif filter:
            await loop.run_in_executor(
                None,
                lambda: self.index.delete(filter=filter, namespace=namespace),
            )
            logger.info("pinecone_delete_filter", filter=filter)

    def get_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        stats = self.index.describe_index_stats()
        return {
            "total_vector_count": stats.total_vector_count,
            "dimension": stats.dimension,
            "namespaces": dict(stats.namespaces) if stats.namespaces else {},
        }


# =============================================================================
# Test Function
# =============================================================================


async def test_connection() -> None:
    """
    Test Pinecone connection and basic operations.

    This function:
    1. Connects to Pinecone
    2. Creates/ensures the index exists
    3. Upserts a sample vector
    4. Queries it back
    5. Deletes the test vector
    """
    import random

    print("=" * 60)
    print("Pinecone Connection Test")
    print("=" * 60)

    client = PineconeClient()
    client.connect()
    print(f"\n[OK] Pinecone client initialized")

    # Ensure index exists
    print(f"\nEnsuring index '{settings.pinecone_index_name}' exists...")
    client.ensure_index(wait_for_ready=True)
    print(f"[OK] Index ready")

    # Get stats
    stats = client.get_stats()
    print(f"[OK] Index stats: {stats['total_vector_count']} vectors, dimension={stats['dimension']}")

    # Create sample vector (3072 dimensions for text-embedding-3-large)
    test_id = "test_vector_001"
    sample_vector = [random.random() for _ in range(PineconeClient.DIMENSION)]

    sample_metadata: ReviewMetadata = {
        "business_id": "biz_sample_001",
        "review_id": "rev_sample_001",
        "rating": 4.5,
        "date": "2024-01-15",
        "platform": "google",
        "sentiment_score": 0.85,
    }

    # Upsert
    print("\nUpserting sample vector...")
    await client.upsert_embeddings([
        {
            "id": test_id,
            "values": sample_vector,
            "metadata": sample_metadata,
        }
    ])
    print(f"[OK] Upserted vector: {test_id}")

    # Wait a moment for indexing
    await asyncio.sleep(2)

    # Query
    print("\nQuerying for similar vectors...")
    results = await client.query(
        vector=sample_vector,
        top_k=5,
        include_metadata=True,
    )
    print(f"[OK] Query returned {len(results)} results:")
    for r in results:
        print(f"  - ID: {r['id']}, Score: {r['score']:.4f}")
        if "metadata" in r:
            print(f"    Metadata: {r['metadata']}")

    # Delete
    print("\nDeleting test vector...")
    await client.delete(ids=[test_id])
    print(f"[OK] Deleted vector: {test_id}")

    # Final stats
    await asyncio.sleep(1)
    stats = client.get_stats()
    print(f"\n[OK] Final stats: {stats['total_vector_count']} vectors")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_connection())
