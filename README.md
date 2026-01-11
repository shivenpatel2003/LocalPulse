# LocalPulse

AI-Powered Restaurant Monitoring & Competitive Intelligence Platform

## Overview

LocalPulse is an intelligent monitoring system that helps restaurant owners and operators track their business performance, monitor competitors, and gain actionable insights from reviews and market data. The platform uses a multi-agent AI architecture combined with knowledge graphs and vector embeddings for comprehensive competitive intelligence.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LocalPulse Platform                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                 │
│  │  Collector   │     │   Analysis   │     │   Delivery   │                 │
│  │   Agents     │────▶│    Agents    │────▶│   Module     │                 │
│  └──────────────┘     └──────────────┘     └──────────────┘                 │
│         │                    │                    │                          │
│         ▼                    ▼                    ▼                          │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │                    Knowledge Layer                       │                │
│  │  ┌─────────────────┐     ┌─────────────────────────┐    │                │
│  │  │ Knowledge Graph │     │   Vector Embeddings     │    │                │
│  │  │   (Entities &   │     │      (pgvector)         │    │                │
│  │  │  Relationships) │     │   Semantic Search       │    │                │
│  │  └─────────────────┘     └─────────────────────────┘    │                │
│  └─────────────────────────────────────────────────────────┘                │
│                              │                                               │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │                    Memory System                         │                │
│  │  ┌───────────┐   ┌───────────┐   ┌───────────────┐      │                │
│  │  │Short-term │   │ Episodic  │   │   Long-term   │      │                │
│  │  │  Memory   │   │  Memory   │   │    Memory     │      │                │
│  │  │  (Cache)  │   │ (Sessions)│   │  (Persistent) │      │                │
│  │  └───────────┘   └───────────┘   └───────────────┘      │                │
│  └─────────────────────────────────────────────────────────┘                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                         ┌──────────────────┐
                         │     Supabase     │
                         │  (PostgreSQL +   │
                         │    pgvector)     │
                         └──────────────────┘
```

### Module Structure

```
src/
├── agents/           # Multi-agent system components
│   ├── base.py       # BaseAgent abstract class
│   ├── analysis.py   # AnalysisAgent for insights
│   ├── orchestrator.py # Workflow coordination
│   └── memory.py     # Tiered memory management
│
├── collectors/       # Data collection agents
│   ├── base.py       # BaseCollector interface
│   ├── google_places.py  # Google Places API
│   ├── reviews.py    # Multi-platform review aggregation
│   └── social.py     # Social media monitoring
│
├── knowledge/        # Knowledge graph & embeddings
│   ├── graph.py      # Knowledge graph operations
│   ├── embeddings.py # Vector embedding store
│   ├── entities.py   # Entity management
│   └── relationships.py # Relationship edges
│
├── delivery/         # Output & notifications
│   ├── reports.py    # Report generation
│   ├── alerts.py     # Real-time alerts
│   └── api.py        # Dashboard API endpoints
│
└── config/           # Configuration management
    └── settings.py   # Pydantic settings
```

### Key Concepts

#### Multi-Agent System

LocalPulse uses specialized agents that work together:

1. **Collector Agents**: Gather data from external sources (Google Places, review platforms, social media)
2. **Analysis Agents**: Process collected data using Claude to generate insights
3. **Orchestrator Agent**: Coordinates workflows and manages agent communication
4. **Memory Agent**: Manages context across the tiered memory system

#### Knowledge Graph

Entities and their relationships are stored in a knowledge graph:

- **Nodes**: Businesses, Reviews, Competitors, Menu Items, Locations
- **Edges**: COMPETES_WITH, HAS_REVIEW, LOCATED_IN, SERVES_CUISINE

#### Vector Embeddings

Semantic search capabilities powered by pgvector:

- Review sentiment analysis
- Similar business discovery
- Trend detection across reviews
- Menu item similarity

#### Tiered Memory System

| Memory Type | Purpose | Retention |
|-------------|---------|-----------|
| Short-term | Current session context | 1 hour |
| Episodic | Recent interactions & events | 30 days |
| Long-term | Persistent knowledge & patterns | Permanent |

## Getting Started

### Prerequisites

- Python 3.11+
- Supabase account with pgvector extension enabled
- Anthropic API key
- OpenAI API key (for embeddings)
- Google Places API key (optional)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-org/localpulse.git
cd localpulse
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

5. Set up Supabase:
```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables (see migrations/ for full schema)
```

### Running the Application

Development mode:
```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with interactive docs at `/docs`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/businesses` | GET/POST | Business management |
| `/api/v1/businesses/{id}/competitors` | GET | Get competitors |
| `/api/v1/reviews` | GET | Query reviews |
| `/api/v1/analysis/insights` | POST | Generate insights |
| `/api/v1/alerts` | GET/POST | Alert management |

## Configuration

Key environment variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_KEY` | Supabase API key | Yes |
| `ANTHROPIC_API_KEY` | Claude API key | Yes |
| `OPENAI_API_KEY` | OpenAI API key (embeddings) | No |
| `GOOGLE_PLACES_API_KEY` | Google Places API | No |

See `.env.example` for all configuration options.

## Development

### Project Structure

- `main.py` - Application entry point
- `src/` - Source code modules
- `tests/` - Test suite
- `migrations/` - Database migrations

### Running Tests

```bash
pytest tests/ -v
```

### Code Style

This project uses:
- `ruff` for linting
- `black` for formatting
- `mypy` for type checking

```bash
ruff check src/
black src/
mypy src/
```

## License

MIT License - See LICENSE file for details.
