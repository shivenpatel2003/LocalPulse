"""
OpenAI Embeddings Service.

Provides text embedding generation using OpenAI's text-embedding-3-large model
with automatic rate limiting, retries, and batch processing.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from openai import AsyncOpenAI, RateLimitError, APIError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings

logger = structlog.get_logger(__name__)


class EmbeddingsService:
    """
    OpenAI embeddings service using text-embedding-3-large.

    Usage:
        service = EmbeddingsService()

        # Single text
        embedding = await service.embed_text("Great food and service!")

        # Batch processing
        embeddings = await service.embed_batch([
            "Excellent pizza",
            "Terrible wait times",
            "Average experience"
        ])
    """

    MODEL = "text-embedding-3-large"
    DIMENSION = 3072
    MAX_BATCH_SIZE = 2048  # OpenAI limit
    MAX_TOKENS_PER_BATCH = 8191  # Approximate token limit

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the embeddings service.

        Args:
            api_key: OpenAI API key. Defaults to settings.openai_api_key.
        """
        self._api_key = api_key or settings.openai_api_key.get_secret_value()
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """Get or create the OpenAI async client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIError)),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda retry_state: logger.warning(
            "openai_retry",
            attempt=retry_state.attempt_number,
            wait=retry_state.next_action.sleep,
        ),
    )
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector (3072 dimensions).
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        response = await self.client.embeddings.create(
            model=self.MODEL,
            input=text,
        )

        embedding = response.data[0].embedding
        logger.debug(
            "embedding_generated",
            text_length=len(text),
            dimension=len(embedding),
        )
        return embedding

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIError)),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda retry_state: logger.warning(
            "openai_retry",
            attempt=retry_state.attempt_number,
            wait=retry_state.next_action.sleep,
        ),
    )
    async def _embed_batch_request(self, texts: list[str]) -> list[list[float]]:
        """
        Internal method to make a batch embedding request.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        response = await self.client.embeddings.create(
            model=self.MODEL,
            input=texts,
        )

        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts with automatic batching.

        Args:
            texts: List of texts to embed.
            batch_size: Number of texts per API call (max 2048).

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
                "embedding_batch_processing",
                batch_num=i // effective_batch_size + 1,
                batch_size=len(batch),
            )

            embeddings = await self._embed_batch_request(batch_texts)

            for idx, embedding in zip(batch_indices, embeddings):
                all_embeddings.append((idx, embedding))

        # Sort by original index and extract embeddings
        all_embeddings.sort(key=lambda x: x[0])
        result = [emb for _, emb in all_embeddings]

        logger.info(
            "embedding_batch_completed",
            total_texts=len(texts),
            processed=len(result),
        )

        return result

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
        }


# =============================================================================
# Test Function
# =============================================================================


async def test_embeddings() -> None:
    """
    Test the embeddings service.

    This function:
    1. Creates an EmbeddingsService instance
    2. Embeds a sample review text
    3. Verifies the embedding dimension is 3072
    4. Prints the first 5 values
    """
    print("=" * 60)
    print("OpenAI Embeddings Test")
    print("=" * 60)

    service = EmbeddingsService()
    print(f"\n[OK] EmbeddingsService initialized (model: {service.MODEL})")

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
    print(f"    Expected:  {EmbeddingsService.DIMENSION}")
    print(f"    Match: {'YES' if len(embedding) == EmbeddingsService.DIMENSION else 'NO'}")
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
    print(f"    All correct dimension: {all(len(e) == 3072 for e in embeddings)}")

    for i, (text, emb) in enumerate(zip(batch_texts, embeddings)):
        print(f"\n    [{i+1}] \"{text[:30]}...\"")
        print(f"        First 3 values: [{emb[0]:.6f}, {emb[1]:.6f}, {emb[2]:.6f}]")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_embeddings())
