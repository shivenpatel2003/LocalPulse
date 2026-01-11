"""
LocalPulse - AI-powered restaurant monitoring and competitive intelligence platform.

This package contains the core modules for the LocalPulse system:
- agents: LangGraph-based multi-agent system (supervisor, collector, analyst, reporter)
- graphs: LangGraph workflow definitions and state machines
- knowledge: Neo4j and Pinecone clients for hybrid retrieval
- memory: Tiered memory system (working, episodic, semantic, graph)
- collectors: Data source integrations (Google Places, social, events, scraping)
- delivery: Report generation, email templates, and visualizations
- api: FastAPI application and endpoints
- config: Pydantic settings and configuration
- models: Data models, schemas, and state definitions
"""

__version__ = "0.1.0"
