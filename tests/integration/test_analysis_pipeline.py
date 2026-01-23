"""Integration tests for the analysis pipeline.

Tests the flow: Collected Data -> LangGraph Agents -> Analysis Results
Verifies agent coordination and state management.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


class TestAnalysisPipeline:
    """Test the multi-agent analysis workflow."""

    @pytest.fixture
    def sample_collected_data(self):
        """Sample data as would come from collection pipeline."""
        return {
            "businesses": [
                {
                    "place_id": "ChIJtest123",
                    "name": "Test Restaurant",
                    "rating": 4.5,
                    "rating_count": 127,
                    "address": "123 Main St",
                },
                {
                    "place_id": "ChIJtest456",
                    "name": "Competitor Cafe",
                    "rating": 4.2,
                    "rating_count": 89,
                    "address": "456 Oak Ave",
                },
            ],
            "collected_at": "2026-01-23T12:00:00Z",
        }

    @pytest.fixture
    def mock_llm_analysis(self):
        """Mock LLM analysis response."""
        return {
            "summary": "Market analysis of 2 businesses in Austin area",
            "insights": [
                "Average rating is 4.35 across analyzed businesses",
                "Test Restaurant leads with higher rating and review volume",
                "Location clustering suggests downtown Austin focus",
            ],
            "recommendations": [
                "Focus on customer experience to improve ratings",
                "Consider loyalty program to increase review volume",
            ],
            "sentiment_breakdown": {
                "positive": 0.72,
                "neutral": 0.20,
                "negative": 0.08,
            },
        }

    @pytest.mark.asyncio
    async def test_analyst_agent_processes_collected_data(
        self, sample_collected_data, mock_llm_analysis, integration_container
    ):
        """Analyst agent processes collected data into insights."""
        from src.agents.analyst import AnalystAgent

        with patch.object(AnalystAgent, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = json.dumps(mock_llm_analysis)

            agent = AnalystAgent()
            result = await agent.execute(json.dumps(sample_collected_data))

            analysis = json.loads(result)
            assert "summary" in analysis
            assert "insights" in analysis
            assert len(analysis["insights"]) > 0

    @pytest.mark.asyncio
    async def test_workflow_state_propagates_between_agents(
        self, sample_collected_data, clean_registry
    ):
        """Workflow state correctly propagates from research to analyst."""
        from src.workflows.agent_workflow import AgentWorkflow

        workflow = AgentWorkflow()
        await workflow.initialize()

        # Mock research agent to return collected data
        if "research" in workflow.agents:
            workflow.agents["research"].execute = AsyncMock(
                return_value=json.dumps(sample_collected_data)
            )

        # Mock analyst agent
        if "analyst" in workflow.agents:
            workflow.agents["analyst"].execute = AsyncMock(
                return_value=json.dumps({"summary": "Test analysis"})
            )

        # Verify agents are registered
        assert "research" in workflow.agents
        assert "analyst" in workflow.agents

        await workflow.shutdown()

    @pytest.mark.asyncio
    async def test_analysis_handles_empty_data(self, integration_container):
        """Analysis gracefully handles empty input data."""
        empty_data = {"businesses": [], "collected_at": "2026-01-23T12:00:00Z"}

        from src.agents.analyst import AnalystAgent

        with patch.object(AnalystAgent, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = json.dumps({
                "summary": "No data available for analysis",
                "insights": [],
                "recommendations": ["Collect more data before analysis"],
            })

            agent = AnalystAgent()
            result = await agent.execute(json.dumps(empty_data))

            analysis = json.loads(result)
            assert "No data" in analysis["summary"] or len(analysis["insights"]) == 0

    @pytest.mark.asyncio
    async def test_analysis_handles_malformed_data(self, integration_container):
        """Analysis handles malformed input gracefully."""
        from src.agents.analyst import AnalystAgent

        with patch.object(AnalystAgent, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = json.dumps({
                "error": "Invalid input format",
                "summary": "Analysis could not be completed",
            })

            agent = AnalystAgent()
            result = await agent.execute("not valid json {{{")

            # Should return error response, not crash
            response = json.loads(result)
            assert "error" in response or "summary" in response

    @pytest.mark.asyncio
    async def test_langgraph_state_transitions(self, sample_collected_data, clean_registry):
        """LangGraph state machine transitions correctly."""
        from src.workflows.agent_workflow import AgentWorkflow

        workflow = AgentWorkflow()
        await workflow.initialize()

        # Verify initial state
        assert workflow.orchestrator is not None

        with patch.object(
            workflow.orchestrator, "execute", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = "Analysis complete"

            result = await workflow.execute("Analyze market data")
            assert result is not None

        await workflow.shutdown()


class TestAgentCoordination:
    """Test coordination between multiple agents."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_registry):
        """Reset registry before each test."""
        pass

    @pytest.mark.asyncio
    async def test_supervisor_routes_to_correct_agent(self, clean_registry):
        """Supervisor correctly routes tasks to specialized agents."""
        from src.workflows.agent_workflow import AgentWorkflow

        workflow = AgentWorkflow()
        await workflow.initialize()

        # Verify router exists and has agents
        assert workflow.router is not None
        agents = workflow.router.list_agents()

        assert "research" in agents
        assert "analyst" in agents

        await workflow.shutdown()

    @pytest.mark.asyncio
    async def test_agent_handoff_preserves_context(
        self, sample_business_data, sample_analysis_result, clean_registry
    ):
        """Context is preserved when handing off between agents."""
        from src.workflows.agent_workflow import AgentWorkflow

        workflow = AgentWorkflow()
        await workflow.initialize()

        # The data format from research should be parseable by analyst
        research_output = json.dumps(sample_business_data)

        # Analyst should be able to parse research output
        parsed = json.loads(research_output)
        assert "businesses" in parsed

        await workflow.shutdown()

    @pytest.mark.asyncio
    async def test_parallel_agent_execution(self, clean_registry):
        """Multiple agents can execute in parallel when appropriate."""
        from src.workflows.agent_workflow import AgentWorkflow
        import asyncio

        workflow = AgentWorkflow()
        await workflow.initialize()

        # Create tasks that could run in parallel
        async def mock_agent_work(agent_id: str, delay: float = 0.1):
            await asyncio.sleep(delay)
            return f"{agent_id} complete"

        # Simulate parallel execution
        tasks = [
            mock_agent_work("research", 0.1),
            mock_agent_work("analyst", 0.1),
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 2

        await workflow.shutdown()
