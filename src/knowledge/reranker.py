"""
Cohere Reranker Service.

Provides document reranking using Cohere's rerank-v3.5 model for improved
relevance scoring in the Adaptive RAG pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict

import structlog
import cohere
from cohere.core import ApiError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings

logger = structlog.get_logger(__name__)


class RerankResult(TypedDict):
    """Result from reranking a document."""

    index: int
    score: float
    text: str


class RerankerService:
    """
    Cohere reranking service using rerank-v3.5.

    Usage:
        service = RerankerService()

        results = await service.rerank(
            query="What's the food quality like?",
            documents=[
                "The pasta was amazing and fresh",
                "Parking was difficult to find",
                "Best steak I've ever had"
            ],
            top_k=3
        )

        for r in results:
            print(f"[{r['score']:.3f}] {r['text']}")
    """

    MODEL = "rerank-v3.5"

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the reranker service.

        Args:
            api_key: Cohere API key. Defaults to settings.cohere_api_key.
        """
        self._api_key = api_key or settings.cohere_api_key.get_secret_value()
        self._client: cohere.AsyncClientV2 | None = None

    @property
    def client(self) -> cohere.AsyncClientV2:
        """Get or create the Cohere async client."""
        if self._client is None:
            self._client = cohere.AsyncClientV2(api_key=self._api_key)
        return self._client

    @retry(
        retry=retry_if_exception_type((ApiError,)),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda retry_state: logger.warning(
            "cohere_retry",
            attempt=retry_state.attempt_number,
            wait=retry_state.next_action.sleep,
        ),
    )
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 10,
    ) -> list[RerankResult]:
        """
        Rerank documents by relevance to query.

        Args:
            query: The search query.
            documents: List of document texts to rerank.
            top_k: Number of top results to return.

        Returns:
            List of reranked results sorted by relevance score (descending).
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        if not documents:
            return []

        # Filter empty documents and track original indices
        valid_docs: list[tuple[int, str]] = [
            (i, doc) for i, doc in enumerate(documents) if doc and doc.strip()
        ]

        if not valid_docs:
            raise ValueError("All documents are empty")

        doc_texts = [doc for _, doc in valid_docs]
        original_indices = [idx for idx, _ in valid_docs]

        # Call Cohere rerank API
        response = await self.client.rerank(
            model=self.MODEL,
            query=query,
            documents=doc_texts,
            top_n=min(top_k, len(doc_texts)),
        )

        # Build results with original indices
        results: list[RerankResult] = []
        for item in response.results:
            original_idx = original_indices[item.index]
            result: RerankResult = {
                "index": original_idx,
                "score": item.relevance_score,
                "text": doc_texts[item.index],
            }
            results.append(result)

        logger.info(
            "rerank_completed",
            query_length=len(query),
            doc_count=len(documents),
            top_k=top_k,
            results=len(results),
        )

        return results

    async def rerank_with_metadata(
        self,
        query: str,
        documents: list[dict[str, Any]],
        text_key: str = "text",
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Rerank documents with metadata preserved.

        Args:
            query: The search query.
            documents: List of dicts containing text and metadata.
            text_key: Key for the text field in each document.
            top_k: Number of top results to return.

        Returns:
            List of original documents with added 'rerank_score' field.
        """
        texts = [doc.get(text_key, "") for doc in documents]
        rerank_results = await self.rerank(query, texts, top_k=top_k)

        # Map scores back to original documents
        results = []
        for r in rerank_results:
            doc = documents[r["index"]].copy()
            doc["rerank_score"] = r["score"]
            doc["rerank_position"] = len(results) + 1
            results.append(doc)

        return results


# =============================================================================
# Test Function
# =============================================================================


async def test_reranker() -> None:
    """
    Test the reranker service.

    This function:
    1. Creates a RerankerService instance
    2. Takes a sample query about food quality
    3. Reranks sample review texts
    4. Shows the reranked order with scores
    """
    print("=" * 60)
    print("Cohere Reranker Test")
    print("=" * 60)

    service = RerankerService()
    print(f"\n[OK] RerankerService initialized (model: {service.MODEL})")

    # Sample query
    query = "How is the food quality and taste?"

    # Sample review texts (intentionally mixed relevance)
    documents = [
        "The parking lot was full and we had to park on the street.",
        "Absolutely delicious! The chef clearly uses fresh, high-quality ingredients.",
        "Our server was friendly but a bit slow with refills.",
        "The pasta was perfectly al dente with a rich, flavorful sauce.",
        "The restaurant has a nice ambiance with dim lighting.",
        "Bland and overcooked. The steak was tough and tasteless.",
        "Great location, right in the heart of downtown.",
        "Best pizza I've ever had - crispy crust and premium toppings!",
        "The wait time was about 20 minutes for a table.",
        "Fresh seafood, amazing flavors, definitely coming back for the lobster.",
    ]

    print(f'\nQuery: "{query}"')
    print(f"\nReranking {len(documents)} documents...")

    results = await service.rerank(query, documents, top_k=5)

    print(f"\n[OK] Top {len(results)} results by relevance:\n")
    print("-" * 60)

    for i, r in enumerate(results, 1):
        score_bar = "#" * int(r["score"] * 20)
        print(f"{i}. [Score: {r['score']:.4f}] {score_bar}")
        print(f"   Original index: {r['index']}")
        print(f'   "{r["text"][:70]}..."')
        print()

    # Test with metadata
    print("-" * 60)
    print("Testing rerank_with_metadata...")

    docs_with_meta = [
        {"text": doc, "source": "google", "rating": 4.0 + i * 0.1}
        for i, doc in enumerate(documents[:5])
    ]

    meta_results = await service.rerank_with_metadata(
        query=query,
        documents=docs_with_meta,
        top_k=3,
    )

    print(f"\n[OK] Results with metadata preserved:\n")
    for r in meta_results:
        print(f"  Position {r['rerank_position']}: score={r['rerank_score']:.4f}")
        print(f"    Source: {r['source']}, Rating: {r['rating']}")
        print(f'    Text: "{r["text"][:50]}..."')
        print()

    print("=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_reranker())
