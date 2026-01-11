# CLAUDE.md - LocalPulse Project Context

This file provides context for Claude Code sessions working on the LocalPulse project.

## Project Overview

LocalPulse is an AI-powered restaurant monitoring and competitive intelligence platform. It uses a multi-agent architecture to collect data, analyze trends, and deliver actionable insights to restaurant owners.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn
- **Database**: Supabase (PostgreSQL with pgvector extension)
- **AI**: Anthropic Claude (analysis), OpenAI (embeddings)
- **External APIs**: Google Places API

## Project Structure

```
localpulse/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variable template
├── src/
│   ├── __init__.py
│   ├── agents/            # Multi-agent system
│   │   ├── __init__.py
│   │   ├── base.py        # BaseAgent abstract class
│   │   ├── analysis.py    # Claude-powered analysis
│   │   ├── orchestrator.py # Agent coordination
│   │   └── memory.py      # Tiered memory management
│   ├── collectors/        # Data collection
│   │   ├── __init__.py
│   │   ├── base.py        # BaseCollector interface
│   │   ├── google_places.py
│   │   └── reviews.py
│   ├── knowledge/         # Knowledge graph & embeddings
│   │   ├── __init__.py
│   │   ├── graph.py       # Entity relationships
│   │   ├── embeddings.py  # pgvector operations
│   │   ├── entities.py
│   │   └── relationships.py
│   ├── delivery/          # Output & notifications
│   │   ├── __init__.py
│   │   ├── reports.py
│   │   ├── alerts.py
│   │   └── api.py
│   └── config/
│       ├── __init__.py
│       └── settings.py    # Pydantic settings
```

## Key Architectural Concepts

### 1. Multi-Agent System

The platform uses specialized agents:

- **Collector Agents** (`src/collectors/`): Gather data from external sources
- **Analysis Agents** (`src/agents/analysis.py`): Use Claude to generate insights
- **Orchestrator** (`src/agents/orchestrator.py`): Coordinates workflows
- **Memory Agent** (`src/agents/memory.py`): Manages tiered memory

### 2. Knowledge Graph

Stores entity relationships in Supabase:

- **Entity Types**: Business, Review, Competitor, MenuItem, Location
- **Relationship Types**: COMPETES_WITH, HAS_REVIEW, LOCATED_IN, SERVES_CUISINE

### 3. Vector Embeddings (pgvector)

Used for semantic search capabilities:

- Review similarity search
- Competitor discovery
- Trend detection

### 4. Tiered Memory System

| Layer | Purpose | TTL |
|-------|---------|-----|
| Short-term | Session context | 1 hour |
| Episodic | Recent events | 30 days |
| Long-term | Persistent knowledge | Permanent |

## Common Development Tasks

### Running the Application

```bash
# Development mode with auto-reload
python main.py

# Or directly with uvicorn
uvicorn main:app --reload
```

### Adding a New Collector

1. Create new file in `src/collectors/`
2. Extend `BaseCollector` class
3. Implement `collect()` and `transform()` methods
4. Register in collector factory

### Adding a New Entity Type

1. Define entity schema in `src/knowledge/entities.py`
2. Add relationship types in `src/knowledge/relationships.py`
3. Create Supabase migration for new table
4. Add embedding generation logic

### Working with Embeddings

```python
from src.knowledge.embeddings import EmbeddingStore

store = EmbeddingStore()
await store.upsert(entity_id, text_content)
similar = await store.search(query_text, limit=10)
```

## Environment Variables

Critical variables that must be set:

- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase anon or service key
- `ANTHROPIC_API_KEY` - For Claude analysis agents
- `OPENAI_API_KEY` - For text-embedding-3-small
- `GOOGLE_PLACES_API_KEY` - For business data collection

## Database Schema (Supabase)

Key tables to be created:

- `businesses` - Restaurant/business entities
- `reviews` - Collected reviews with embeddings
- `competitors` - Competitor relationships
- `knowledge_edges` - Knowledge graph edges
- `memory_short_term` - Short-term memory cache
- `memory_episodic` - Episodic memory store
- `memory_long_term` - Long-term memory store

## API Structure

Base URL: `http://localhost:8000`

- `GET /health` - Health check
- `GET /docs` - Swagger UI (development only)
- `GET/POST /api/v1/businesses` - Business CRUD
- `GET /api/v1/reviews` - Review queries
- `POST /api/v1/analysis/insights` - Generate insights
- `GET/POST /api/v1/alerts` - Alert management

## Code Conventions

- Use `async/await` for all I/O operations
- Type hints required for all functions
- Use `structlog` for logging
- Follow Pydantic models for data validation
- Error handling with custom exception classes

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src
```

## Current Status / TODOs

The project structure is set up. Next steps:

1. Implement `BaseAgent` and `BaseCollector` abstract classes
2. Set up Supabase schema migrations
3. Implement Google Places collector
4. Build the knowledge graph operations
5. Create the analysis agent with Claude
6. Build the tiered memory system
7. Add API routes for all endpoints
8. Implement the alert system
