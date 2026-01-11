"""
LangGraph Workflow Definitions.

This module contains the workflow graphs that define agent orchestration:

- main: Primary workflow graph connecting all agents
- collection: Data collection subgraph for gathering external data
- analysis: Analysis pipeline subgraph for processing and insight generation

Workflows are defined as StateGraph instances with typed state,
conditional edges, and support for human-in-the-loop patterns.

Example:
    from src.graphs import create_main_graph

    graph = create_main_graph()
    compiled = graph.compile()
    result = await compiled.ainvoke(initial_state)
"""
