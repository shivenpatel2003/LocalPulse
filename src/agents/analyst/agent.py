"""Analyst Agent for data analysis and insight generation.

Processes data from Research Agent and generates actionable insights.
"""

import json
from typing import Optional

from src.agents.base import BaseAgent, AgentConfig


class AnalystAgent(BaseAgent):
    """Agent specialized in analyzing business data.

    Receives JSON data from Research Agent and produces:
    - Sentiment analysis
    - Trend identification
    - Competitive insights
    - Recommendations
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                agent_id="analyst",
                name="Analyst Agent",
                description="Analyzes business data and generates insights",
                model="claude-sonnet-4-20250514",
                temperature=0.5,
            )
        super().__init__(config)

    async def execute(self, query: str) -> str:
        """Execute analysis on provided data.

        Args:
            query: Analysis request, may include JSON data.

        Returns:
            JSON string with analysis results.

        Raises:
            RuntimeError: If agent is not initialized.
            Exception: Re-raises any execution errors after logging.
        """
        self._ensure_initialized()

        try:
            return await self._execute_core(query)
        except Exception as e:
            self.logger.error(
                "analyst_execution_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Re-raise to fail loudly - caller should handle
            raise

    async def _execute_core(self, query: str) -> str:
        """Core analysis logic."""
        # Placeholder - would use LLM for actual analysis
        return json.dumps({
            "summary": "Analysis completed",
            "insights": [],
            "recommendations": [],
            "source": "analyst_agent",
        })
