"""
LangGraph Agent Definitions.

This module contains the multi-agent system powered by LangGraph:

- supervisor: Orchestrator agent that routes tasks and manages workflow state
- collector: Data collection agent that interfaces with external APIs
- analyst: Analysis agent powered by Claude for insight generation
- reporter: Report generation agent for creating deliverables

The agents follow a supervisor-worker pattern where the supervisor
delegates tasks to specialized worker agents based on the current
workflow state and user requirements.

Example:
    from src.agents import SupervisorAgent, CollectorAgent

    supervisor = SupervisorAgent()
    result = await supervisor.run(task="analyze_competitor", target="restaurant_id")
"""
