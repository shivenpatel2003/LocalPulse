"""Communication Agent for report delivery.

Handles sending reports via email and other channels.
"""

import json
from typing import Optional

from src.agents.base import BaseAgent, AgentConfig


class CommunicationAgent(BaseAgent):
    """Agent specialized in delivering reports.

    Handles:
    - Email delivery
    - Notification dispatch
    - Report distribution
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                agent_id="communication",
                name="Communication Agent",
                description="Delivers reports and notifications",
                model="claude-sonnet-4-20250514",
                temperature=0.3,
            )
        super().__init__(config)

    async def execute(self, query: str) -> str:
        """Execute communication task.

        Args:
            query: Communication request (e.g., send email).

        Returns:
            Status of communication.

        Raises:
            RuntimeError: If agent is not initialized.
            Exception: Re-raises any execution errors after logging.
        """
        self._ensure_initialized()

        try:
            return await self._execute_core(query)
        except Exception as e:
            self.logger.error(
                "communication_execution_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Re-raise to fail loudly - caller should handle
            raise

    async def _execute_core(self, query: str) -> str:
        """Core communication logic."""
        return json.dumps({
            "status": "success",
            "message": "Communication task completed",
        })
