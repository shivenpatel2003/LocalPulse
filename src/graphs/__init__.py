"""
LangGraph Workflow Definitions.

This module contains the workflow graphs that define agent orchestration:

- main: Primary workflow graph connecting all agents
- collection: Data collection subgraph for gathering external data
- analysis: Analysis pipeline subgraph for processing and insight generation

Workflows are defined as StateGraph instances with typed state,
conditional edges, and support for human-in-the-loop patterns.

Example:
    from src.graphs import create_main_graph, MasterState, create_master_state

    graph = create_main_graph()
    compiled = graph.compile()
    initial_state = create_master_state(
        client_id="123",
        business_name="Local Bistro"
    )
    result = await compiled.ainvoke(initial_state)
"""

from src.graphs.state import (
    # Status enums
    AnalysisStatus,
    CollectionStatus,
    ReportStatus,
    WorkflowPhase,
    # State types
    AnalysisState,
    CollectionState,
    MasterState,
    ReportState,
    SentimentResult,
    ThemeResult,
    # Factory functions
    create_analysis_state,
    create_collection_state,
    create_master_state,
    create_report_state,
)

from src.graphs.collection_graph import (
    compile_collection_graph,
    create_collection_graph,
    run_collection,
    test_collection_workflow,
)

from src.graphs.analysis_graph import (
    compile_analysis_graph,
    create_analysis_graph,
    run_analysis,
    test_analysis_workflow,
    # Structured output models
    SentimentAnalysisResult,
    ThemeAnalysisResult,
    CompetitorAnalysisResult,
    InsightsResult,
    RecommendationsResult,
)

from src.graphs.report_graph import (
    compile_report_graph,
    create_report_graph,
    run_report,
    test_report_workflow,
)

from src.graphs.master_graph import (
    compile_master_graph,
    create_master_graph,
    run_full_pipeline,
    run_batch_pipeline,
    test_master_workflow,
    PipelineResult,
)

__all__ = [
    # Status enums
    "CollectionStatus",
    "AnalysisStatus",
    "ReportStatus",
    "WorkflowPhase",
    # State types
    "CollectionState",
    "AnalysisState",
    "ReportState",
    "MasterState",
    "SentimentResult",
    "ThemeResult",
    # Factory functions
    "create_collection_state",
    "create_analysis_state",
    "create_report_state",
    "create_master_state",
    # Collection graph
    "create_collection_graph",
    "compile_collection_graph",
    "run_collection",
    "test_collection_workflow",
    # Analysis graph
    "create_analysis_graph",
    "compile_analysis_graph",
    "run_analysis",
    "test_analysis_workflow",
    # Analysis output models
    "SentimentAnalysisResult",
    "ThemeAnalysisResult",
    "CompetitorAnalysisResult",
    "InsightsResult",
    "RecommendationsResult",
    # Report graph
    "create_report_graph",
    "compile_report_graph",
    "run_report",
    "test_report_workflow",
    # Master graph
    "create_master_graph",
    "compile_master_graph",
    "run_full_pipeline",
    "run_batch_pipeline",
    "test_master_workflow",
    "PipelineResult",
]
