"""Research Agent for competitive intelligence data collection.

Specializes in collecting business data, market research, competitor analysis,
and social media monitoring. Returns JSON-formatted responses for downstream
agent consumption.
"""

import json
from typing import Any, Dict, List, Optional

from src.agents.base import BaseAgent, AgentConfig
from src.agents.research.tools import (
    collect_business_data,
    search_competitors,
    analyze_market,
    monitor_social,
)


class ResearchAgent(BaseAgent):
    """Agent specialized in competitive intelligence research.

    Provides tools for:
    - Business data collection from Google Places
    - Competitor discovery and analysis
    - Market research and trends
    - Social media monitoring

    All tools return JSON-formatted strings for Analyst Agent compatibility.
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                agent_id="research",
                name="Research Agent",
                description="Collects competitive intelligence data from multiple sources",
                model="claude-sonnet-4-20250514",
                temperature=0.3,  # Lower temp for consistent data formatting
                system_prompt=self._get_system_prompt(),
            )
        super().__init__(config)

        # Bind research tools
        self.bind_tools([
            collect_business_data,
            search_competitors,
            analyze_market,
            monitor_social,
        ])

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the Research Agent."""
        return """You are a Research Agent specializing in competitive intelligence.

Your capabilities:
1. collect_business_data - Gather business information from Google Places
2. search_competitors - Find and analyze competitor businesses
3. analyze_market - Research market trends and opportunities
4. monitor_social - Track social media mentions and sentiment

Always return data in JSON format with provenance fields (source, collected_at).
When collecting data, be thorough but respect rate limits.
Focus on actionable intelligence that helps businesses compete effectively."""

    async def execute(self, query: str) -> str:
        """Execute a research query and return JSON results.

        Args:
            query: Research query describing what to collect/analyze.

        Returns:
            JSON string with research results and provenance.
        """
        try:
            result = await self._execute_core(query)
            return result
        except Exception as e:
            self.logger.error("research_execution_error", error=str(e))
            return json.dumps({
                "error": str(e),
                "query": query,
                "source": "research_agent",
            })

    async def _execute_core(self, query: str) -> str:
        """Core execution logic for research queries.

        Analyzes the query to determine which tool(s) to use,
        then executes and returns combined results.
        """
        query_lower = query.lower()

        # Route to appropriate tool based on query
        if "competitor" in query_lower:
            return await search_competitors.ainvoke({
                "query": query,
                "location": self._extract_location(query),
                "limit": 10,
            })
        elif "social" in query_lower or "twitter" in query_lower or "instagram" in query_lower:
            return await monitor_social.ainvoke({
                "query": query,
                "platforms": ["twitter", "instagram"],
                "limit": 50,
            })
        elif "market" in query_lower or "trend" in query_lower:
            return await analyze_market.ainvoke({
                "query": query,
                "location": self._extract_location(query),
            })
        else:
            # Default to business data collection
            return await collect_business_data.ainvoke({
                "query": query,
                "location": self._extract_location(query),
                "limit": 20,
            })

    def _extract_location(self, query: str) -> str:
        """Extract location from query string."""
        # Simple extraction - look for common patterns
        common_locations = [
            "Austin", "TX", "Texas",
            "New York", "NY",
            "San Francisco", "CA",
            "Los Angeles", "LA",
            "Chicago", "IL",
            "Manchester", "London", "UK",
        ]
        for loc in common_locations:
            if loc.lower() in query.lower():
                return loc
        return ""
