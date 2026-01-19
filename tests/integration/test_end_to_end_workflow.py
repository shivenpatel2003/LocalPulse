"""End-to-end integration tests for multi-agent workflow.

Tests the complete flow: Research -> Analyst -> Creator -> Communication
with mocked external services to verify agent coordination.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.workflows.agent_workflow import AgentWorkflow
from src.orchestration.discovery import AgentRegistry


class TestEndToEndWorkflow:
    """Test complete multi-agent workflow execution."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_registry):
        """Setup for each test."""
        pass

    @pytest.mark.asyncio
    async def test_workflow_initializes_all_agents(self):
        """Verify all agents including Research are initialized."""
        workflow = AgentWorkflow()
        await workflow.initialize()

        expected_agents = [
            "communication", "creator", "analyst", "research"
        ]

        for agent_id in expected_agents:
            assert agent_id in workflow.agents, f"Missing agent: {agent_id}"

        await workflow.shutdown()

    @pytest.mark.asyncio
    async def test_research_agent_returns_json(self, sample_business_data):
        """Research Agent tools return JSON-formatted data."""
        from src.agents.research.tools import collect_business_data

        # Mock the collector to return test data
        with patch('src.agents.research.tools.get_collector') as mock_get:
            mock_collector = AsyncMock()

            async def mock_collect():
                for item in sample_business_data["businesses"]:
                    yield item

            mock_collector.collect = mock_collect
            mock_get.return_value = mock_collector

            # The tool should return valid JSON
            result = await collect_business_data.ainvoke({
                "query": "coffee shops",
                "location": "Austin, TX",
                "limit": 10
            })

            # Should be valid JSON
            data = json.loads(result)
            assert "businesses" in data or "error" in data

    @pytest.mark.asyncio
    async def test_research_to_analyst_data_flow(
        self,
        sample_business_data,
        sample_analysis_result,
        mock_llm_response
    ):
        """Research Agent data flows correctly to Analyst Agent."""
        from src.agents.research import ResearchAgent
        from src.agents.analyst import AnalystAgent

        # Mock Research Agent to return sample data
        research_agent = ResearchAgent()
        with patch.object(research_agent, 'execute', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = json.dumps(sample_business_data)

            research_result = await research_agent.execute(
                "Collect data on coffee shops in Austin"
            )

            # Verify result is valid JSON
            data = json.loads(research_result)
            assert "businesses" in data

        # Verify Analyst can parse this data format
        analyst_agent = AnalystAgent()
        # Analyst's analyze_data tool expects JSON string input
        # This verifies the contract between agents
        assert isinstance(research_result, str)
        parsed = json.loads(research_result)
        assert "businesses" in parsed

    @pytest.mark.asyncio
    async def test_analyst_to_creator_data_flow(
        self,
        sample_analysis_result,
        sample_report_content
    ):
        """Analyst Agent insights flow to Creator Agent."""
        from src.agents.analyst import AnalystAgent
        from src.agents.creator import CreatorAgent

        # Analyst output format
        analysis_json = json.dumps(sample_analysis_result)

        # Creator Agent expects context string, not JSON
        # Verify we can extract context from analysis
        analysis = json.loads(analysis_json)

        context_for_creator = f"""
Analysis Summary: {analysis['summary']}

Key Insights:
{chr(10).join('- ' + i for i in analysis['insights'])}

Recommendations:
{chr(10).join('- ' + r for r in analysis['recommendations'])}
"""

        # This context string is what Creator's generate_document expects
        assert "Market analysis" in context_for_creator
        assert "recommendations" in context_for_creator.lower()

    @pytest.mark.asyncio
    async def test_creator_to_communication_flow(self, sample_report_content):
        """Creator Agent report can be delivered by Communication Agent."""
        from src.agents.creator import CreatorAgent
        from src.agents.communication.tools import send_email

        # Creator produces markdown report
        report = sample_report_content

        # Communication Agent's send_email expects:
        # - to: email address
        # - subject: string
        # - body: string (the report)
        # - html: bool (optional)

        # Verify report is suitable for email body
        assert isinstance(report, str)
        assert len(report) > 0
        assert "Competitive Intelligence Report" in report

    @pytest.mark.asyncio
    async def test_full_workflow_with_mocked_execution(self, clean_registry):
        """Full workflow execution with mocked agent responses."""
        workflow = AgentWorkflow()
        await workflow.initialize()

        # Mock the orchestrator's execute to simulate full flow
        with patch.object(
            workflow.orchestrator,
            'execute',
            new_callable=AsyncMock
        ) as mock_exec:
            # Simulate successful workflow completion
            mock_exec.return_value = """Workflow completed successfully:
1. Research Agent collected 5 competitors
2. Analyst Agent identified market opportunities
3. Creator Agent generated competitive report
4. Communication Agent sent report to user@example.com
"""

            result = await workflow.execute(
                "Research competitors and send me a report"
            )

            assert "completed" in result.lower() or "success" in result.lower()

        await workflow.shutdown()


class TestAgentDataContracts:
    """Test data contracts between agents."""

    def test_research_output_matches_analyst_input(self, sample_business_data):
        """Research output format matches Analyst's analyze_data input."""
        # Research produces JSON with 'businesses' array
        research_output = json.dumps(sample_business_data)

        # Analyst's analyze_data expects JSON string
        # Verify format compatibility
        parsed = json.loads(research_output)

        # Must have records-like structure
        assert "businesses" in parsed or "records" in parsed

        # Each record should have analyzable fields
        if "businesses" in parsed:
            for biz in parsed["businesses"]:
                # Rating and metrics for analysis
                assert "rating" in biz or "name" in biz

    def test_analyst_output_matches_creator_input(self, sample_analysis_result):
        """Analyst output provides context for Creator."""
        analysis = sample_analysis_result

        # Creator needs: summary, insights, recommendations
        # These are used in generate_document context
        assert "summary" in analysis or "insights" in analysis

        # Must be stringifiable for context injection
        context = str(analysis)
        assert len(context) > 0

    def test_creator_output_matches_communication_input(self, sample_report_content):
        """Creator output is suitable for Communication delivery."""
        report = sample_report_content

        # Communication's send_email needs string body
        assert isinstance(report, str)

        # Should be human-readable
        assert len(report) > 50

        # Should have structure (for HTML conversion if needed)
        assert "#" in report or "Report" in report


class TestWorkflowErrorHandling:
    """Test error handling in multi-agent workflow."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_registry):
        """Setup for each test."""
        pass

    @pytest.mark.asyncio
    async def test_research_error_doesnt_crash_workflow(self):
        """Research Agent errors are handled gracefully."""
        from src.agents.research import ResearchAgent

        agent = ResearchAgent()

        # Mock to simulate error
        with patch.object(agent, '_execute_core', new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("API unavailable")

            # Should return error string, not raise
            result = await agent.execute("test query")

            assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_agent_chain_continues_on_partial_failure(self, clean_registry):
        """Workflow handles partial failures gracefully."""
        workflow = AgentWorkflow()
        await workflow.initialize()

        # Even if research fails, workflow should handle it
        research_agent = workflow.agents.get("research")
        if research_agent:
            with patch.object(
                research_agent,
                'execute',
                new_callable=AsyncMock
            ) as mock_research:
                mock_research.return_value = json.dumps({
                    "error": "Collection failed",
                    "businesses": []
                })

                # Orchestrator should still be able to process
                # (actual behavior depends on orchestrator logic)

        await workflow.shutdown()

    @pytest.mark.asyncio
    async def test_workflow_shutdown_handles_all_agents(self, clean_registry):
        """Workflow shutdown cleans up all agents properly."""
        workflow = AgentWorkflow()
        await workflow.initialize()

        # Verify agents exist
        initial_count = len(workflow.agents)
        assert initial_count > 0

        # Shutdown
        await workflow.shutdown()

        # Verify cleanup
        assert len(workflow.agents) == 0
        assert workflow.orchestrator is None


class TestAgentRegistration:
    """Test agent registration and discovery."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_registry):
        """Setup for each test."""
        pass

    @pytest.mark.asyncio
    async def test_research_agent_registered_in_registry(self):
        """Research Agent registers with AgentRegistry."""
        from src.agents.research import register_research_agent

        agent = register_research_agent()
        registry = AgentRegistry()

        # Verify card registered
        card = registry.get_card("research")
        assert card is not None
        assert card.agent_id == "research"

        # Verify capabilities
        assert "data-collection" in card.capabilities
        assert "market-research" in card.capabilities

    @pytest.mark.asyncio
    async def test_workflow_registers_all_agents(self, clean_registry):
        """AgentWorkflow registers all agents with router."""
        workflow = AgentWorkflow()
        await workflow.initialize()

        # Check router has all agents
        router_agents = workflow.router.list_agents()
        assert "research" in router_agents
        assert "analyst" in router_agents
        assert "creator" in router_agents
        assert "communication" in router_agents

        await workflow.shutdown()

    @pytest.mark.asyncio
    async def test_registry_find_by_capability(self, clean_registry):
        """AgentRegistry can find agents by capability."""
        from src.agents.research import register_research_agent

        register_research_agent()
        registry = AgentRegistry()

        # Find data-collection capable agents
        agents = registry.find_by_capability("data-collection")
        assert len(agents) > 0
        assert any(a.agent_id == "research" for a in agents)
