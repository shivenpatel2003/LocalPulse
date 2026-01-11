"""
Knowledge Module

This module manages the knowledge graph and vector embeddings:
- KnowledgeGraph: Entity relationships (businesses, reviews, competitors)
- EmbeddingStore: Vector embeddings using pgvector for semantic search
- EntityManager: CRUD operations for knowledge entities
- RelationshipManager: Manages edges between entities
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import KnowledgeGraph
    from .embeddings import EmbeddingStore
    from .entities import EntityManager
    from .relationships import RelationshipManager

__all__ = [
    "KnowledgeGraph",
    "EmbeddingStore",
    "EntityManager",
    "RelationshipManager",
]
