"""
Cohere Embeddings Service.

Provides text embedding generation using Cohere's embed-v3 model
with automatic rate limiting, retries, and batch processing.

This is a drop-in replacement for OpenAI embeddings with free tier support.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import cohere
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings

logger = structlog.get_logger(__name__)

# Thread pool for sync Cohere client
_executor = ThreadPoolExecutor(max_workers=4)


def _is_retryable(exception: BaseException) -> bool:
    """Check if exception should trigger retry."""
    error_str = str(exception).lower()
    return any(keyword in error_str for keyword in ["rate", "limit", "timeout", "unavailable"])


class CohereEmbeddingsService:
    """
    Cohere embeddings service using configurable embed model.

    Free tier: 1000 API calls/month (trial key)
    Dimension: 1024 (default) or 384/512/768/1024 (configurable via settings)

    Usage:
        service = CohereEmbeddingsService()

        # Single text
        embedding = await service.embed_text("Great food and service!")

        # Batch processing
        embeddings = await service.embed_batch([
            "Excellent pizza",
            "Terrible wait times",
            "Average experience"
        ])
    """

    MAX_BATCH_SIZE = 96  # Cohere limit per request
    INPUT_TYPE_DOCUMENT = "search_document"
    INPUT_TYPE_QUERY = "search_query"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ) -> None:
        """
        Initialize the Cohere embeddings service.

        Args:
            api_key: Cohere API key. Defaults to settings.cohere_api_key.
            model: Embedding model. Defaults to settings.cohere_embedding_model.
            dimension: Embedding dimension. Defaults to settings.cohere_embedding_dimension.
        """
        self._api_key = api_key or settings.cohere_api_key.get_secret_value()
        self._model = model or settings.cohere_embedding_model
        self._dimension = dimension or settings.cohere_embedding_dimension
        self._client: cohere.ClientV2 | None = None

        logger.info(
            "cohere_embeddings_initialized",
            model=self._model,
            dimension=self._dimension,
        )

    @property
    def MODEL(self) -> str:
        """Get the embedding model name."""
        return self._model

    @property
    def DIMENSION(self) -> int:
        """Get the embedding dimension."""
        return self._dimension

    @property
    def client(self) -> cohere.ClientV2:
        """Get or create the Cohere client."""
        if self._client is None:
            self._client = cohere.ClientV2(api_key=self._api_key)
        return self._client

    def _embed_sync(
        self,
        texts: list[str],
        input_type: str = INPUT_TYPE_DOCUMENT,
    ) -> list[list[float]]:
        """Synchronous embedding call."""
        response = self.client.embed(
            model=self._model,
            texts=texts,
            input_type=input_type,
            embedding_types=["float"],
        )
        return response.embeddings.float_

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda retry_state: logger.warning(
            "cohere_retry",
            attempt=retry_state.attempt_number,
            wait=retry_state.next_action.sleep if retry_state.next_action else 0,
        ),
    )
    async def embed_text(
        self,
        text: str,
        input_type: str = INPUT_TYPE_DOCUMENT,
    ) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed.
            input_type: Either "search_document" (for storing) or
                       "search_query" (for searching).

        Returns:
            Embedding vector (1024 dimensions by default).
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            _executor,
            lambda: self._embed_sync([text], input_type),
        )

        embedding = embeddings[0]
        logger.debug(
            "cohere_embedding_generated",
            text_length=len(text),
            dimension=len(embedding),
        )
        return embedding

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda retry_state: logger.warning(
            "cohere_retry",
            attempt=retry_state.attempt_number,
            wait=retry_state.next_action.sleep if retry_state.next_action else 0,
        ),
    )
    async def _embed_batch_request(
        self,
        texts: list[str],
        input_type: str = INPUT_TYPE_DOCUMENT,
    ) -> list[list[float]]:
        """
        Internal method to make a batch embedding request.

        Args:
            texts: List of texts to embed.
            input_type: Document or query type.

        Returns:
            List of embedding vectors.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self._embed_sync(texts, input_type),
        )

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 96,
        input_type: str = INPUT_TYPE_DOCUMENT,
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts with automatic batching.

        Args:
            texts: List of texts to embed.
            batch_size: Number of texts per API call (max 96).
            input_type: Document or query type.

        Returns:
            List of embedding vectors in same order as input.
        """
        if not texts:
            return []

        # Filter empty texts and track indices
        valid_texts: list[tuple[int, str]] = [
            (i, t) for i, t in enumerate(texts) if t and t.strip()
        ]

        if not valid_texts:
            raise ValueError("All texts are empty")

        # Process in batches
        all_embeddings: list[tuple[int, list[float]]] = []
        effective_batch_size = min(batch_size, self.MAX_BATCH_SIZE)

        for i in range(0, len(valid_texts), effective_batch_size):
            batch = valid_texts[i : i + effective_batch_size]
            batch_indices = [idx for idx, _ in batch]
            batch_texts = [text for _, text in batch]

            logger.debug(
                "cohere_embedding_batch_processing",
                batch_num=i // effective_batch_size + 1,
                batch_size=len(batch),
            )

            embeddings = await self._embed_batch_request(batch_texts, input_type)

            for idx, embedding in zip(batch_indices, embeddings):
                all_embeddings.append((idx, embedding))

        # Sort by original index and extract embeddings
        all_embeddings.sort(key=lambda x: x[0])
        result = [emb for _, emb in all_embeddings]

        logger.info(
            "cohere_embedding_batch_completed",
            total_texts=len(texts),
            processed=len(result),
        )

        return result

    async def embed_query(self, query: str) -> list[float]:
        """
        Generate embedding for a search query.

        Uses input_type="search_query" for optimal retrieval performance.

        Args:
            query: Query text to embed.

        Returns:
            Embedding vector optimized for searching.
        """
        return await self.embed_text(query, input_type=self.INPUT_TYPE_QUERY)

    async def embed_with_metadata(
        self,
        text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate embedding with associated metadata.

        Args:
            text: Text to embed.
            metadata: Metadata to include.

        Returns:
            Dict with 'embedding' and 'metadata' keys.
        """
        embedding = await self.embed_text(text)
        return {
            "embedding": embedding,
            "metadata": metadata,
            "text_length": len(text),
            "model": self.MODEL,
            "dimension": self._dimension,
        }


# =============================================================================
# Test Function
# =============================================================================


async def test_cohere_embeddings() -> None:
    """
    Test the Cohere embeddings service.
    """
    print("=" * 60)
    print("Cohere Embeddings Test")
    print("=" * 60)

    service = CohereEmbeddingsService()
    print(f"\n[OK] CohereEmbeddingsService initialized (model: {service.MODEL})")

    # Test single embedding
    sample_text = (
        "The pasta was absolutely delicious! Fresh ingredients, "
        "perfect al dente texture, and the sauce was rich and flavorful. "
        "Our server was attentive and friendly. Will definitely come back!"
    )

    print(f"\nEmbedding sample text ({len(sample_text)} chars)...")
    print(f'Text: "{sample_text[:60]}..."')

    embedding = await service.embed_text(sample_text)

    print(f"\n[OK] Embedding generated")
    print(f"    Dimension: {len(embedding)}")
    print(f"    Expected:  {service.DIMENSION}")
    print(f"    Match: {'YES' if len(embedding) == service.DIMENSION else 'NO'}")
    print(f"\n    First 5 values: {embedding[:5]}")

    # Test batch embedding
    print("\n" + "-" * 40)
    print("Testing batch embedding...")

    batch_texts = [
        "Great pizza, fast delivery!",
        "Terrible service, waited an hour.",
        "Average food, nothing special.",
        "Best sushi in town!",
    ]

    embeddings = await service.embed_batch(batch_texts)

    print(f"\n[OK] Batch embeddings generated")
    print(f"    Count: {len(embeddings)}")
    print(f"    All correct dimension: {all(len(e) == service.DIMENSION for e in embeddings)}")

    for i, (text, emb) in enumerate(zip(batch_texts, embeddings)):
        print(f"\n    [{i+1}] \"{text[:30]}...\"")
        print(f"        First 3 values: [{emb[0]:.6f}, {emb[1]:.6f}, {emb[2]:.6f}]")

    # Test query embedding
    print("\n" + "-" * 40)
    print("Testing query embedding (search_query type)...")

    query = "best pizza restaurants"
    query_embedding = await service.embed_query(query)
    print(f"\n[OK] Query embedding generated")
    print(f"    Dimension: {len(query_embedding)}")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_cohere_embeddings())
