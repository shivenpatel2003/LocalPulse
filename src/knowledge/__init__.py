"""
Knowledge Infrastructure.

This module provides the knowledge layer combining graph and vector databases:

- neo4j_client: Neo4j connection management and Cypher query execution
- pinecone_client: Pinecone vector store operations (upsert, query, delete)
- cohere_embeddings: Text embedding generation using Cohere embed-v3 (FREE tier)
- embeddings: Legacy OpenAI embeddings (requires paid account)
- reranker: Cohere Rerank integration for relevance scoring

The knowledge layer implements Adaptive RAG with hybrid retrieval:
1. Vector search in Pinecone for semantic similarity
2. Graph traversal in Neo4j for relationship-based retrieval
3. Reranking with Cohere for optimal context assembly

Example:
    from src.knowledge import Neo4jClient, PineconeClient, EmbeddingsService

    neo4j = Neo4jClient()
    pinecone = PineconeClient()
    embeddings = EmbeddingsService()  # Uses Cohere by default

    # Hybrid retrieval
    vector_results = await pinecone.query(embedding, top_k=20)
    graph_results = await neo4j.get_related_entities(entity_id)
    reranked = await reranker.rerank(query, vector_results + graph_results)
"""

from src.knowledge.neo4j_client import (
    Neo4jClient,
    create_sample_business,
    create_sample_location,
    initialize_schema,
    test_connection as test_neo4j_connection,
)
from src.knowledge.pinecone_client import (
    PineconeClient,
    ReviewMetadata,
    VectorRecord,
    test_connection as test_pinecone_connection,
)
# Use Cohere embeddings as default (free tier, 1024 dimensions)
from src.knowledge.cohere_embeddings import (
    CohereEmbeddingsService as EmbeddingsService,
    test_cohere_embeddings as test_embeddings,
)
# Keep OpenAI available for users with paid accounts
from src.knowledge.embeddings import (
    EmbeddingsService as OpenAIEmbeddingsService,
    test_embeddings as test_openai_embeddings,
)
from src.knowledge.reranker import (
    RerankerService,
    RerankResult,
    test_reranker,
)

__all__ = [
    # Neo4j
    "Neo4jClient",
    "initialize_schema",
    "create_sample_business",
    "create_sample_location",
    "test_neo4j_connection",
    # Pinecone
    "PineconeClient",
    "ReviewMetadata",
    "VectorRecord",
    "test_pinecone_connection",
    # Embeddings (Cohere - default)
    "EmbeddingsService",
    "test_embeddings",
    # Embeddings (OpenAI - legacy)
    "OpenAIEmbeddingsService",
    "test_openai_embeddings",
    # Reranker
    "RerankerService",
    "RerankResult",
    "test_reranker",
]
