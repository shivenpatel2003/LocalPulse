# LocalPulse

**AI-powered restaurant monitoring and competitive intelligence platform**

LocalPulse helps restaurant owners understand their competitive landscape, track customer sentiment, and receive actionable insights through an intelligent multi-agent system.

## Features

- **Competitive Monitoring** - Track competitors' reviews, menu changes, and events
- **Sentiment Analysis** - AI-powered analysis of customer reviews and social mentions
- **Knowledge Graph** - Rich entity relationships for deep market understanding
- **Automated Reports** - Weekly insights delivered to your inbox
- **Real-time Alerts** - Instant notifications for significant changes

## Architecture

LocalPulse uses a state-of-the-art AI architecture:

- **Multi-Agent System** - LangGraph-powered agents for collection, analysis, and reporting
- **Adaptive RAG** - Hybrid retrieval combining vector search and graph traversal
- **Tiered Memory** - Working, episodic, semantic, and graph memory layers
- **Knowledge Graph** - Neo4j for entity relationships and pattern discovery

## Tech Stack

- **AI/ML**: LangGraph, LangChain, Claude API, OpenAI Embeddings, Cohere Rerank
- **Databases**: Neo4j (graph), Pinecone (vectors), Redis (cache)
- **Backend**: FastAPI, Python 3.11+
- **Deployment**: Docker, Google Cloud Run

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- Docker & Docker Compose
- API keys (see `.env.example`)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/localpulse.git
cd localpulse

# Install dependencies
poetry install

# Copy environment template
cp .env.example .env
# Edit .env with your API keys

# Start infrastructure (Neo4j, Redis)
docker-compose up -d neo4j redis

# Run the application
poetry run uvicorn src.api.main:app --reload
```

### Docker Development

```bash
# Build and run everything
docker-compose up -d

# View logs
docker-compose logs -f app
```

## Project Structure

```
localpulse/
├── src/
│   ├── agents/        # LangGraph agents
│   ├── graphs/        # Workflow definitions
│   ├── knowledge/     # Neo4j, Pinecone, embeddings
│   ├── memory/        # Tiered memory system
│   ├── collectors/    # Data source integrations
│   ├── delivery/      # Reports and notifications
│   ├── api/           # FastAPI application
│   ├── config/        # Settings
│   └── models/        # Data models
├── tests/
├── scripts/
└── infrastructure/
```

## Development

```bash
# Run tests
poetry run pytest

# Type checking
poetry run mypy src/

# Linting
poetry run ruff check src/

# Format code
poetry run ruff format src/
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## License

MIT License - see LICENSE for details.
