# CLAUDE.md - LocalPulse Project Context

This file provides context for Claude Code sessions working on the LocalPulse project.

## Project Overview

**LocalPulse** is an AI-powered restaurant monitoring and competitive intelligence platform. It uses a state-of-the-art multi-agent architecture to collect data from multiple sources, build a knowledge graph of the restaurant ecosystem, and deliver actionable insights to restaurant owners.

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Knowledge Graph** | Neo4j (entities, relationships, graph traversal) |
| **Vector Store** | Pinecone (semantic search, embeddings) |
| **Agent Framework** | LangGraph + LangChain (multi-agent orchestration) |
| **LLM** | Claude API (Anthropic) |
| **Embeddings** | OpenAI text-embedding-3-small |
| **Reranking** | Cohere Rerank |
| **API Framework** | FastAPI + Uvicorn |
| **Deployment** | Google Cloud Run (containerized) |
| **Caching** | Redis |

## Architecture

### Multi-Agent System (LangGraph)

The platform uses a **supervisor-worker pattern** with specialized agents:

```
┌─────────────────────────────────────────────────────────────┐
│                    SUPERVISOR AGENT                         │
│         (Routes tasks, manages workflow state)              │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│ COLLECTOR │  │  ANALYST  │  │  MEMORY   │  │ REPORTER  │
│   AGENT   │  │   AGENT   │  │   AGENT   │  │   AGENT   │
└───────────┘  └───────────┘  └───────────┘  └───────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
 Google Places   Claude API    Neo4j +       Email/Reports
 Yelp, Social    Analysis      Pinecone      Visualization
```

### Adaptive RAG Pipeline

Implements a sophisticated retrieval strategy:

1. **Query Analysis** - Classify query intent and complexity
2. **Hybrid Retrieval** - Combine vector search (Pinecone) + graph traversal (Neo4j)
3. **Reranking** - Cohere Rerank for relevance scoring
4. **Context Assembly** - Build optimal context window
5. **Generation** - Claude API with structured outputs

### Tiered Memory System

| Layer | Storage | Purpose | TTL |
|-------|---------|---------|-----|
| **Working** | Redis | Current session context | Session |
| **Episodic** | Neo4j + Pinecone | Recent events, interactions | 30 days |
| **Semantic** | Pinecone | Factual knowledge embeddings | Permanent |
| **Graph** | Neo4j | Entity relationships, structure | Permanent |

## Project Structure

```
localpulse/
├── CLAUDE.md              # This file
├── README.md              # Project documentation
├── pyproject.toml         # Poetry dependencies
├── Dockerfile             # Container definition
├── docker-compose.yml     # Local development stack
├── .env.example           # Environment template
│
├── src/
│   ├── agents/            # LangGraph agent definitions
│   │   ├── supervisor.py  # Orchestrator agent
│   │   ├── collector.py   # Data collection agent
│   │   ├── analyst.py     # Analysis agent (Claude)
│   │   └── reporter.py    # Report generation agent
│   │
│   ├── graphs/            # LangGraph workflow definitions
│   │   ├── main.py        # Primary workflow graph
│   │   ├── collection.py  # Data collection subgraph
│   │   └── analysis.py    # Analysis pipeline subgraph
│   │
│   ├── knowledge/         # Knowledge infrastructure
│   │   ├── neo4j_client.py    # Neo4j connection & queries
│   │   ├── pinecone_client.py # Pinecone operations
│   │   ├── embeddings.py      # Embedding generation
│   │   └── reranker.py        # Cohere reranking
│   │
│   ├── memory/            # Tiered memory system
│   │   ├── working.py     # Session memory (Redis)
│   │   ├── episodic.py    # Event memory
│   │   ├── semantic.py    # Factual memory
│   │   └── graph.py       # Relationship memory
│   │
│   ├── collectors/        # Data source integrations
│   │   ├── google_places.py
│   │   ├── social.py
│   │   ├── events.py
│   │   └── scraper.py
│   │
│   ├── delivery/          # Output generation
│   │   ├── templates/     # Jinja2 email templates
│   │   ├── charts.py      # Plotly visualizations
│   │   └── reports.py     # Report builder
│   │
│   ├── api/               # FastAPI application
│   │   ├── main.py        # App entry point
│   │   ├── routes/        # API endpoints
│   │   └── middleware/    # Auth, logging, etc.
│   │
│   ├── config/            # Configuration
│   │   └── settings.py    # Pydantic settings
│   │
│   └── models/            # Data models
│       ├── entities.py    # Business, Review, etc.
│       ├── schemas.py     # API schemas
│       └── state.py       # LangGraph state definitions
│
├── tests/                 # Test suite
├── scripts/               # Utility scripts
└── infrastructure/        # IaC (Terraform, etc.)
```

## Key Patterns

### LangGraph State Management

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    context: dict
    current_agent: str
    iteration: int
```

### Neo4j Entity Model

```cypher
(:Business)-[:COMPETES_WITH]->(:Business)
(:Business)-[:HAS_REVIEW]->(:Review)
(:Business)-[:LOCATED_IN]->(:Location)
(:Business)-[:SERVES]->(:Cuisine)
(:Review)-[:MENTIONS]->(:Topic)
```

### Pinecone Namespace Strategy

- `reviews` - Review embeddings
- `businesses` - Business descriptions
- `insights` - Generated insights
- `queries` - Query cache

## Development Commands

```bash
# Install dependencies
poetry install

# Run locally
poetry run uvicorn src.api.main:app --reload

# Run tests
poetry run pytest

# Type checking
poetry run mypy src/

# Linting
poetry run ruff check src/

# Docker development
docker-compose up -d
```

## Environment Variables

See `.env.example` for all required variables. Critical ones:

- `ANTHROPIC_API_KEY` - Claude API access
- `OPENAI_API_KEY` - Embeddings
- `PINECONE_API_KEY` - Vector store
- `NEO4J_URI` / `NEO4J_PASSWORD` - Graph database
- `GOOGLE_PLACES_API_KEY` - Business data

## Current Status

Project structure initialized. Implementation order:

1. [ ] Core configuration and settings
2. [ ] Neo4j and Pinecone clients
3. [ ] Base agent definitions
4. [ ] LangGraph workflow setup
5. [ ] Collector implementations
6. [ ] Memory system
7. [ ] Analysis pipeline
8. [ ] API endpoints
9. [ ] Delivery system
10. [ ] Testing and documentation
