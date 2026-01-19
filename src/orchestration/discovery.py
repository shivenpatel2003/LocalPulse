"""Agent discovery and registry for multi-agent orchestration.

Provides singleton registry for agent registration, discovery, and routing.
"""

from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.base import BaseAgent


class AgentCard:
    """Metadata card describing an agent's capabilities."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        capabilities: List[str],
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self.input_schema = input_schema or {}
        self.output_schema = output_schema or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


class AgentRegistry:
    """Singleton registry for agent discovery and routing.

    Maintains a registry of all available agents with their capabilities,
    enabling the orchestrator to route tasks to appropriate agents.
    """

    _instance: Optional["AgentRegistry"] = None
    _cards: Dict[str, AgentCard] = {}
    _agents: Dict[str, "BaseAgent"] = {}

    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._cards = {}
            cls._agents = {}
        return cls._instance

    @classmethod
    def reset_registry(cls) -> None:
        """Reset the registry state. Primarily for testing."""
        cls._cards = {}
        cls._agents = {}
        cls._instance = None

    def register_card(self, card: AgentCard) -> None:
        """Register an agent card for discovery."""
        self._cards[card.agent_id] = card

    def register_agent(self, agent_id: str, agent: "BaseAgent") -> None:
        """Register an agent instance."""
        self._agents[agent_id] = agent

    def get_card(self, agent_id: str) -> Optional[AgentCard]:
        """Get agent card by ID."""
        return self._cards.get(agent_id)

    def get_agent(self, agent_id: str) -> Optional["BaseAgent"]:
        """Get agent instance by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        return list(self._cards.keys())

    def find_by_capability(self, capability: str) -> List[AgentCard]:
        """Find agents with a specific capability."""
        return [
            card for card in self._cards.values()
            if capability in card.capabilities
        ]

    def get_all_cards(self) -> List[AgentCard]:
        """Get all registered agent cards."""
        return list(self._cards.values())
