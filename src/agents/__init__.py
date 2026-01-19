"""
LangGraph Agent Definitions.

This module contains the multi-agent system powered by LangGraph:

- research: Research agent for competitive intelligence data collection
- analyst: Analysis agent powered by Claude for insight generation
- creator: Content creation agent for report generation
- communication: Communication agent for report delivery

The agents follow a supervisor-worker pattern where the supervisor
delegates tasks to specialized worker agents based on the current
workflow state and user requirements.

Example:
    from src.agents import ResearchAgent, AnalystAgent

    research = ResearchAgent()
    result = await research.execute("Find coffee shops in Austin")
"""

from src.agents.base import BaseAgent, AgentConfig
from src.agents.research import ResearchAgent
from src.agents.analyst import AnalystAgent
from src.agents.creator import CreatorAgent
from src.agents.communication import CommunicationAgent

__all__ = [
    "BaseAgent",
    "AgentConfig",
    "ResearchAgent",
    "AnalystAgent",
    "CreatorAgent",
    "CommunicationAgent",
]
