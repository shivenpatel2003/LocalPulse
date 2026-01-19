"""Multi-agent workflow orchestration.

Coordinates the Research -> Analyst -> Creator -> Communication agent chain
for complete competitive intelligence workflows.
"""

from typing import Any, Dict, List, Optional
import structlog

from src.orchestration.discovery import AgentRegistry, AgentCard
from src.agents.base import BaseAgent

logger = structlog.get_logger(__name__)


class MessageRouter:
    """Routes messages between agents based on capabilities."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent_id: str, agent: BaseAgent) -> None:
        """Register an agent for message routing."""
        self._agents[agent_id] = agent

    def get_agent_instance(self, agent_id: str) -> Optional[BaseAgent]:
        """Get agent instance by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        return list(self._agents.keys())


class Orchestrator:
    """Orchestrates multi-agent workflows.

    Routes tasks to appropriate agents based on capabilities
    and manages the flow between agents.
    """

    def __init__(self, agents: Dict[str, BaseAgent]):
        self.agents = agents
        self.logger = logger.bind(component="orchestrator")

    async def execute(self, query: str) -> str:
        """Execute a workflow based on the query.

        Routes to appropriate agent(s) and chains results.

        Args:
            query: User query describing the task.

        Returns:
            Final result from workflow execution.
        """
        query_lower = query.lower()

        # Determine workflow based on query
        if "research" in query_lower or "collect" in query_lower or "competitor" in query_lower:
            # Research-focused workflow
            return await self._research_workflow(query)
        elif "analyze" in query_lower:
            return await self._analysis_workflow(query)
        elif "report" in query_lower:
            return await self._report_workflow(query)
        else:
            # Default: full pipeline
            return await self._full_workflow(query)

    async def _research_workflow(self, query: str) -> str:
        """Execute research-focused workflow."""
        research = self.agents.get("research")
        if research:
            return await research.execute(query)
        return "Research agent not available"

    async def _analysis_workflow(self, query: str) -> str:
        """Execute analysis-focused workflow."""
        analyst = self.agents.get("analyst")
        if analyst:
            return await analyst.execute(query)
        return "Analyst agent not available"

    async def _report_workflow(self, query: str) -> str:
        """Execute report generation workflow."""
        creator = self.agents.get("creator")
        if creator:
            return await creator.execute(query)
        return "Creator agent not available"

    async def _full_workflow(self, query: str) -> str:
        """Execute full Research -> Analyst -> Creator -> Communication workflow."""
        results = []

        # Step 1: Research
        research = self.agents.get("research")
        if research:
            self.logger.info("workflow_research_start")
            research_result = await research.execute(query)
            results.append(f"Research: {research_result[:200]}...")

        # Step 2: Analysis
        analyst = self.agents.get("analyst")
        if analyst and research_result:
            self.logger.info("workflow_analysis_start")
            analysis_result = await analyst.execute(research_result)
            results.append(f"Analysis: {analysis_result[:200]}...")

        # Step 3: Create report
        creator = self.agents.get("creator")
        if creator:
            self.logger.info("workflow_create_start")
            report = await creator.execute(str(results))
            results.append(f"Report: Generated")

        # Step 4: Communicate
        communication = self.agents.get("communication")
        if communication:
            self.logger.info("workflow_communicate_start")
            send_result = await communication.execute("Send report")
            results.append(f"Communication: {send_result}")

        return "\n".join(results)


class AgentWorkflow:
    """Multi-agent workflow manager.

    Initializes and coordinates all agents for end-to-end workflows.
    Supports Research -> Analyst -> Creator -> Communication chain.
    """

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.router = MessageRouter()
        self.orchestrator: Optional[Orchestrator] = None
        self.registry = AgentRegistry()
        self.logger = logger.bind(component="agent_workflow")

    async def initialize(self) -> None:
        """Initialize all agents and the orchestrator."""
        self.logger.info("initializing_agents")

        # Import and create agents
        from src.agents.communication import CommunicationAgent
        from src.agents.creator import CreatorAgent
        from src.agents.analyst import AnalystAgent
        from src.agents.research import register_research_agent

        # Initialize standard agents
        communication = CommunicationAgent()
        await communication.initialize()
        self.agents["communication"] = communication
        self.router.register("communication", communication)

        creator = CreatorAgent()
        await creator.initialize()
        self.agents["creator"] = creator
        self.router.register("creator", creator)

        analyst = AnalystAgent()
        await analyst.initialize()
        self.agents["analyst"] = analyst
        self.router.register("analyst", analyst)

        # Register research agent (also registers with AgentRegistry)
        research = register_research_agent()
        await research.initialize()
        self.agents["research"] = research
        self.router.register("research", research)

        # Create orchestrator with all agents
        self.orchestrator = Orchestrator(self.agents)

        self.logger.info(
            "agents_initialized",
            agent_count=len(self.agents),
            agents=list(self.agents.keys()),
        )

    async def shutdown(self) -> None:
        """Shutdown all agents gracefully."""
        self.logger.info("shutting_down_agents")

        for agent_id, agent in self.agents.items():
            try:
                await agent.shutdown()
                self.logger.debug("agent_shutdown", agent_id=agent_id)
            except Exception as e:
                self.logger.error(
                    "agent_shutdown_error",
                    agent_id=agent_id,
                    error=str(e),
                )

        self.agents.clear()
        self.orchestrator = None

    async def execute(self, query: str) -> str:
        """Execute a workflow query.

        Args:
            query: User query describing the task.

        Returns:
            Result from workflow execution.
        """
        if not self.orchestrator:
            return "Workflow not initialized. Call initialize() first."

        return await self.orchestrator.execute(query)

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Get an agent by ID."""
        return self.agents.get(agent_id)

    def list_agents(self) -> List[str]:
        """List all initialized agent IDs."""
        return list(self.agents.keys())
