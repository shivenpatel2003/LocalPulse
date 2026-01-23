"""Base agent class for all LocalPulse agents.

Provides common interface for agent lifecycle, execution, and tool management.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import structlog

from src.core.exceptions import InitializationError

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
        """Initialize the agent. Override for custom setup.

        Raises:
            InitializationError: If initialization fails.
        """
        try:
            await self._do_initialize()
            self._initialized = True
            self.logger.info("agent_initialized")
        except Exception as e:
            self.logger.error(
                "agent_initialization_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise InitializationError(
                self.config.name,
                f"Failed to initialize agent: {e}",
                {"agent_id": self.agent_id, "original_error": str(e)},
            )

    async def _do_initialize(self) -> None:
        """Override in subclasses for custom initialization logic."""
        pass

    async def shutdown(self) -> None:
        """Shutdown the agent. Override for cleanup."""
        self._initialized = False
        self.logger.info("agent_shutdown")

    def bind_tools(self, tools: List[Any]) -> None:
        """Bind tools to the agent."""
        self.tools = tools
        self.logger.info("tools_bound", tool_count=len(tools))

    def _ensure_initialized(self) -> None:
        """Ensure agent is initialized before execution.

        Raises:
            RuntimeError: If agent is not initialized.
        """
        if not self._initialized:
            self.logger.error("agent_not_initialized", agent_id=self.agent_id)
            raise RuntimeError(
                f"Agent '{self.name}' not initialized. Call initialize() first."
            )

    @abstractmethod
    async def execute(self, query: str) -> str:
        """Execute a task and return result.

        Args:
            query: The task or query to execute.

        Returns:
            String result of execution.

        Raises:
            RuntimeError: If agent is not initialized.
        """
        pass

    async def _execute_core(self, query: str) -> str:
        """Core execution logic. Override in subclasses.

        Raises:
            NotImplementedError: If not overridden.
        """
        raise NotImplementedError("Subclasses must implement _execute_core")
