"""
Tiered Memory System.

This module implements a sophisticated memory architecture with four layers:

- working: Short-term session memory stored in Redis (TTL: session)
- episodic: Recent events and interactions stored in Neo4j + Pinecone (TTL: 30 days)
- semantic: Factual knowledge embeddings in Pinecone (permanent)
- graph: Entity relationships and structure in Neo4j (permanent)

The memory system enables:
- Context persistence across agent interactions
- Temporal reasoning about past events
- Semantic retrieval of relevant knowledge
- Relationship-aware memory access

Example:
    from src.memory import WorkingMemory, EpisodicMemory, SemanticMemory

    working = WorkingMemory(session_id="user_123")
    await working.store("current_task", task_data)

    episodic = EpisodicMemory()
    await episodic.record_event("review_collected", event_data)

    semantic = SemanticMemory()
    relevant = await semantic.retrieve("competitor pricing strategies", top_k=5)
"""
