"""Base agent class for all LocalPulse agents.

Provides common interface for agent lifecycle, execution, and tool management.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class AgentConfig:
    """Configuration for an agent."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt


class BaseAgent(ABC):
    """Base class for all agents in the LocalPulse system.

    Provides lifecycle management, tool binding, and execution interface.
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.tools: List[Any] = []
        self._initialized = False
        self.logger = logger.bind(agent_id=config.agent_id)

    @property
    def agent_id(self) -> str:
        """Get the agent's unique identifier."""
        return self.config.agent_id

    @property
    def name(self) -> str:
        """Get the agent's display name."""
        return self.config.name

    async def initialize(self) -> None:
        """Initialize the agent. Override for custom setup."""
        self._initialized = True
        self.logger.info("agent_initialized")

    async def shutdown(self) -> None:
        """Shutdown the agent. Override for cleanup."""
        self._initialized = False
        self.logger.info("agent_shutdown")

    def bind_tools(self, tools: List[Any]) -> None:
        """Bind tools to the agent."""
        self.tools = tools
        self.logger.info("tools_bound", tool_count=len(tools))

    @abstractmethod
    async def execute(self, query: str) -> str:
        """Execute a task and return result.

        Args:
            query: The task or query to execute.

        Returns:
            String result of execution.
        """
        pass

    async def _execute_core(self, query: str) -> str:
        """Core execution logic. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _execute_core")
