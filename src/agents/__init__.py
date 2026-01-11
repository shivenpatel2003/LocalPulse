"""
Agents Module

This module contains the multi-agent system components:
- BaseAgent: Abstract base class for all agents
- AnalysisAgent: Performs competitive analysis and insight generation
- OrchestratorAgent: Coordinates multiple agents and manages workflows
- MemoryAgent: Manages tiered memory (short-term, episodic, long-term)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseAgent
    from .analysis import AnalysisAgent
    from .orchestrator import OrchestratorAgent
    from .memory import MemoryAgent

__all__ = [
    "BaseAgent",
    "AnalysisAgent",
    "OrchestratorAgent",
    "MemoryAgent",
]
