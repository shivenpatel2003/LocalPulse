"""Research Agent module for competitive intelligence data collection.

Provides ResearchAgent with tools for:
- Business data collection (Google Places)
- Market research and analysis
- Competitor discovery and tracking
- Social media monitoring
"""

from src.agents.research.agent import ResearchAgent
from src.agents.research.tools import (
    collect_business_data,
    search_competitors,
    analyze_market,
    monitor_social,
)

__all__ = [
    "ResearchAgent",
    "collect_business_data",
    "search_competitors",
    "analyze_market",
    "monitor_social",
]


def register_research_agent() -> ResearchAgent:
    """Create and register ResearchAgent with the AgentRegistry.

    Returns:
        Configured ResearchAgent instance.
    """
    from src.orchestration.discovery import AgentRegistry, AgentCard

    agent = ResearchAgent()

    # Register agent card for discovery
    card = AgentCard(
        agent_id="research",
        name="Research Agent",
        description="Collects competitive intelligence data from multiple sources including Google Places, social media, and web sources.",
        capabilities=[
            "data-collection",
            "market-research",
            "competitor-analysis",
            "social-monitoring",
        ],
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research query or task"},
                "location": {"type": "string", "description": "Geographic location"},
                "limit": {"type": "integer", "description": "Max results to return"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "businesses": {"type": "array"},
                "count": {"type": "integer"},
                "source": {"type": "string"},
                "collected_at": {"type": "string"},
            },
        },
    )

    registry = AgentRegistry()
    registry.register_card(card)
    registry.register_agent("research", agent)

    return agent
