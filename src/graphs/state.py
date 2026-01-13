"""LangGraph state definitions for LocalPulse workflows.

This module defines the typed state containers used by LangGraph to manage
workflow execution across the multi-agent system.

State Flow:
    MasterState (orchestrator)
    ├── CollectionState (data gathering)
    ├── AnalysisState (insight generation)
    └── ReportState (report delivery)
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


# =============================================================================
# Status Enums
# =============================================================================


class CollectionStatus(str, Enum):
    """Status values for collection workflow."""
    PENDING = "pending"
    COLLECTING = "collecting"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisStatus(str, Enum):
    """Status values for analysis workflow."""
    PENDING = "pending"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportStatus(str, Enum):
    """Status values for report workflow."""
    PENDING = "pending"
    GENERATING = "generating"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowPhase(str, Enum):
    """Current phase in the master workflow."""
    COLLECTION = "collection"
    ANALYSIS = "analysis"
    REPORTING = "reporting"
    COMPLETE = "complete"


# =============================================================================
# Reducer Functions
# =============================================================================


def merge_lists(left: list, right: list) -> list:
    """Merge two lists, appending right to left."""
    return left + right


def replace_value(left: Any, right: Any) -> Any:
    """Replace left value with right (standard assignment)."""
    return right


# =============================================================================
# Collection Workflow State
# =============================================================================


class CollectionState(TypedDict, total=False):
    """State for the data collection workflow.

    This state tracks the progress of collecting reviews and competitor
    data from various sources (Google Places, social media, etc.).

    Attributes:
        business_id: Unique identifier for the target business.
        business_name: Human-readable name of the business.
        google_place_id: Google Places API identifier for the business.
        reviews_collected: List of review dicts collected from all sources.
        competitors_found: List of competitor business dicts discovered.
        errors: List of error messages encountered during collection.
        status: Current status of the collection workflow.
        started_at: Timestamp when collection began.
        completed_at: Timestamp when collection finished (success or failure).
    """
    business_id: str
    business_name: str
    google_place_id: Optional[str]
    reviews_collected: Annotated[list[dict[str, Any]], merge_lists]
    competitors_found: Annotated[list[dict[str, Any]], merge_lists]
    errors: Annotated[list[str], merge_lists]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]


# =============================================================================
# Analysis Workflow State
# =============================================================================


class SentimentResult(TypedDict):
    """Structure for sentiment analysis results."""
    overall_score: float
    positive_count: int
    negative_count: int
    neutral_count: int
    trend: str  # "improving", "declining", "stable"


class ThemeResult(TypedDict):
    """Structure for theme extraction results."""
    theme: str
    count: int
    sentiment: float
    example_reviews: list[str]


class AnalysisState(TypedDict, total=False):
    """State for the analysis workflow.

    This state tracks the progress of analyzing collected data to
    extract insights, sentiment, themes, and recommendations.

    Attributes:
        business_id: Unique identifier for the business being analyzed.
        reviews: List of review dicts to analyze.
        sentiment_results: Aggregated sentiment analysis results.
        theme_results: Extracted themes with counts and sentiment.
        competitor_analysis: Comparative analysis with competitors.
        insights: List of key insights extracted from the data.
        recommendations: AI-generated actionable recommendations.
        errors: List of error messages encountered during analysis.
        status: Current status of the analysis workflow.
    """
    business_id: str
    reviews: list[dict[str, Any]]
    sentiment_results: dict[str, Any]
    theme_results: Annotated[list[dict[str, Any]], merge_lists]
    competitor_analysis: dict[str, Any]
    insights: Annotated[list[str], merge_lists]
    recommendations: Annotated[list[str], merge_lists]
    errors: Annotated[list[str], merge_lists]
    status: str


# =============================================================================
# Report Workflow State
# =============================================================================


class ReportState(TypedDict, total=False):
    """State for the report generation workflow.

    This state tracks the progress of generating and delivering
    reports based on the analysis results.

    Attributes:
        business_id: Unique identifier for the business.
        analysis: Complete analysis results to include in report.
        report_html: Generated HTML content for the report.
        report_data: Structured data for programmatic access.
        email_sent: Whether the report email was successfully sent.
        errors: List of error messages encountered during reporting.
        status: Current status of the report workflow.
    """
    business_id: str
    analysis: dict[str, Any]
    report_html: str
    report_data: dict[str, Any]
    email_sent: bool
    errors: Annotated[list[str], merge_lists]
    status: str


# =============================================================================
# Master Orchestrator State
# =============================================================================


class MasterState(TypedDict, total=False):
    """State for the master orchestrator workflow.

    This is the top-level state that coordinates all sub-workflows
    (collection, analysis, reporting) and tracks overall progress.

    Attributes:
        client_id: Unique identifier for the client business.
        messages: Conversation history for agent communication.
        collection_state: Nested state for collection workflow.
        analysis_state: Nested state for analysis workflow.
        report_state: Nested state for report workflow.
        current_phase: Current phase of the overall workflow.
        errors: List of top-level error messages.
    """
    client_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    collection_state: CollectionState
    analysis_state: AnalysisState
    report_state: ReportState
    current_phase: str
    errors: Annotated[list[str], merge_lists]


# =============================================================================
# State Factory Functions
# =============================================================================


def create_collection_state(
    business_id: str,
    business_name: str,
    google_place_id: Optional[str] = None,
) -> CollectionState:
    """Create an initialized CollectionState.

    Args:
        business_id: Unique identifier for the business.
        business_name: Human-readable business name.
        google_place_id: Optional Google Places ID.

    Returns:
        Initialized CollectionState with default values.
    """
    return CollectionState(
        business_id=business_id,
        business_name=business_name,
        google_place_id=google_place_id,
        reviews_collected=[],
        competitors_found=[],
        errors=[],
        status=CollectionStatus.PENDING.value,
        started_at=datetime.utcnow(),
        completed_at=None,
    )


def create_analysis_state(
    business_id: str,
    reviews: Optional[list[dict[str, Any]]] = None,
) -> AnalysisState:
    """Create an initialized AnalysisState.

    Args:
        business_id: Unique identifier for the business.
        reviews: Optional list of reviews to analyze.

    Returns:
        Initialized AnalysisState with default values.
    """
    return AnalysisState(
        business_id=business_id,
        reviews=reviews or [],
        sentiment_results={},
        theme_results=[],
        competitor_analysis={},
        insights=[],
        recommendations=[],
        errors=[],
        status=AnalysisStatus.PENDING.value,
    )


def create_report_state(
    business_id: str,
    analysis: Optional[dict[str, Any]] = None,
) -> ReportState:
    """Create an initialized ReportState.

    Args:
        business_id: Unique identifier for the business.
        analysis: Optional analysis results to include.

    Returns:
        Initialized ReportState with default values.
    """
    return ReportState(
        business_id=business_id,
        analysis=analysis or {},
        report_html="",
        report_data={},
        email_sent=False,
        errors=[],
        status=ReportStatus.PENDING.value,
    )


def create_master_state(
    client_id: str,
    business_name: str,
    google_place_id: Optional[str] = None,
) -> MasterState:
    """Create an initialized MasterState with all sub-states.

    Args:
        client_id: Unique identifier for the client.
        business_name: Human-readable business name.
        google_place_id: Optional Google Places ID.

    Returns:
        Fully initialized MasterState with nested sub-states.
    """
    return MasterState(
        client_id=client_id,
        messages=[],
        collection_state=create_collection_state(
            business_id=client_id,
            business_name=business_name,
            google_place_id=google_place_id,
        ),
        analysis_state=create_analysis_state(business_id=client_id),
        report_state=create_report_state(business_id=client_id),
        current_phase=WorkflowPhase.COLLECTION.value,
        errors=[],
    )
