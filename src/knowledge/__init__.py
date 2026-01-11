"""
Knowledge Infrastructure.

This module provides the knowledge layer combining graph and vector databases:

- neo4j_client: Neo4j connection management and Cypher query execution
- pinecone_client: Pinecone vector store operations (upsert, query, delete)
- embeddings: Text embedding generation using OpenAI text-embedding-3-small
- reranker: Cohere Rerank integration for relevance scoring

The knowledge layer implements Adaptive RAG with hybrid retrieval:
1. Vector search in Pinecone for semantic similarity
2. Graph traversal in Neo4j for relationship-based retrieval
3. Reranking with Cohere for optimal context assembly

Example:
    from src.knowledge import Neo4jClient, PineconeClient, EmbeddingService

    neo4j = Neo4jClient()
    pinecone = PineconeClient()
    embeddings = EmbeddingService()

    # Hybrid retrieval
    vector_results = await pinecone.query(embedding, top_k=20)
    graph_results = await neo4j.get_related_entities(entity_id)
    reranked = await reranker.rerank(query, vector_results + graph_results)
"""
