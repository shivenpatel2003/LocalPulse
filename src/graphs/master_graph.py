"""Master orchestrator that chains all LocalPulse workflows.

This module provides the top-level orchestration that:
1. Runs the Collection workflow (gather data from Google Places)
2. Runs the Analysis workflow (AI-powered insights with Claude)
3. Runs the Report workflow (generate and send HTML report)

Includes error handling, retry logic, and batch processing capabilities.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

import structlog
from langgraph.graph import END, StateGraph

from src.graphs.state import (
    MasterState,
    WorkflowPhase,
    CollectionStatus,
    AnalysisStatus,
    ReportStatus,
    create_master_state,
    create_collection_state,
    create_analysis_state,
    create_report_state,
)
from src.graphs.collection_graph import compile_collection_graph
from src.graphs.analysis_graph import compile_analysis_graph
from src.graphs.report_graph import compile_report_graph

logger = structlog.get_logger(__name__)


# =============================================================================
# Pipeline Result Models
# =============================================================================


class PipelineResult:
    """Result container for pipeline execution."""

    def __init__(
        self,
        business_name: str,
        business_id: str,
        success: bool = False,
        phase_completed: str = "none",
        collection_summary: Optional[dict] = None,
        analysis_summary: Optional[dict] = None,
        report_summary: Optional[dict] = None,
        errors: Optional[list[str]] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ):
        self.business_name = business_name
        self.business_id = business_id
        self.success = success
        self.phase_completed = phase_completed
        self.collection_summary = collection_summary or {}
        self.analysis_summary = analysis_summary or {}
        self.report_summary = report_summary or {}
        self.errors = errors or []
        self.started_at = started_at
        self.completed_at = completed_at

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "business_name": self.business_name,
            "business_id": self.business_id,
            "success": self.success,
            "phase_completed": self.phase_completed,
            "collection_summary": self.collection_summary,
            "analysis_summary": self.analysis_summary,
            "report_summary": self.report_summary,
            "errors": self.errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.started_at and self.completed_at
                else None
            ),
        }


# =============================================================================
# Master Workflow Node Functions
# =============================================================================


async def run_collection_phase(state: MasterState) -> dict:
    """Execute the collection workflow phase.

    Gathers business data, reviews, and competitor information
    from Google Places API.

    Args:
        state: Current master state.

    Returns:
        Partial state update with collection results.
    """
    client_id = state.get("client_id", "unknown")
    collection_state = state.get("collection_state", {})
    business_name = collection_state.get("business_name", "Unknown Business")

    logger.info(
        "master_collection_start",
        client_id=client_id,
        business_name=business_name,
    )

    try:
        # Compile and run collection graph
        collection_graph = compile_collection_graph()

        # Create initial collection state
        initial_state = create_collection_state(
            business_id=client_id,
            business_name=business_name,
            google_place_id=collection_state.get("google_place_id"),
        )

        # Run collection workflow
        final_collection_state = await collection_graph.ainvoke(initial_state)

        # Check for failures
        status = final_collection_state.get("status", CollectionStatus.FAILED.value)
        errors = final_collection_state.get("errors", [])

        if status == CollectionStatus.FAILED.value:
            logger.error(
                "master_collection_failed",
                client_id=client_id,
                errors=errors,
            )
            return {
                "collection_state": final_collection_state,
                "current_phase": WorkflowPhase.COLLECTION.value,
                "errors": errors,
            }

        # Extract summary data
        reviews = final_collection_state.get("reviews_collected", [])
        competitors = final_collection_state.get("competitors_found", [])
        review_count = len([r for r in reviews if r.get("type") == "review"])
        competitor_count = len(competitors)

        logger.info(
            "master_collection_complete",
            client_id=client_id,
            review_count=review_count,
            competitor_count=competitor_count,
        )

        return {
            "collection_state": final_collection_state,
            "current_phase": WorkflowPhase.ANALYSIS.value,
        }

    except Exception as e:
        logger.error("master_collection_error", client_id=client_id, error=str(e))
        return {
            "errors": [f"Collection phase error: {str(e)}"],
            "current_phase": WorkflowPhase.COLLECTION.value,
        }


async def run_analysis_phase(state: MasterState) -> dict:
    """Execute the analysis workflow phase.

    Performs AI-powered sentiment analysis, theme extraction,
    competitor comparison, and generates insights/recommendations.

    Args:
        state: Current master state with collection data.

    Returns:
        Partial state update with analysis results.
    """
    client_id = state.get("client_id", "unknown")
    collection_state = state.get("collection_state", {})

    logger.info("master_analysis_start", client_id=client_id)

    try:
        # Extract business info from collection
        reviews_collected = collection_state.get("reviews_collected", [])
        competitors_found = collection_state.get("competitors_found", [])

        # Get business details
        business_details = next(
            (r for r in reviews_collected if r.get("type") == "business_details"),
            {},
        )
        business_name = business_details.get("name") or collection_state.get("business_name", "Unknown")
        google_place_id = collection_state.get("google_place_id")

        # Compile and run analysis graph
        analysis_graph = compile_analysis_graph()

        # Create initial analysis state
        initial_state = create_analysis_state(
            business_id=google_place_id or client_id,
            reviews=[r for r in reviews_collected if r.get("type") == "review"],
        )

        # Add business context to state
        initial_state["sentiment_results"] = {
            "business_name": business_name,
            "business_rating": business_details.get("rating"),
            "review_count": len([r for r in reviews_collected if r.get("type") == "review"]),
        }
        initial_state["competitor_analysis"] = {
            "competitors": competitors_found,
            "business_name": business_name,
            "business_rating": business_details.get("rating"),
        }

        # Run analysis workflow
        final_analysis_state = await analysis_graph.ainvoke(initial_state)

        # Check for failures
        status = final_analysis_state.get("status", AnalysisStatus.FAILED.value)
        errors = final_analysis_state.get("errors", [])

        # Even with some errors, we may have partial results
        has_insights = len(final_analysis_state.get("insights", [])) > 0
        has_recommendations = len(final_analysis_state.get("recommendations", [])) > 0

        if status == AnalysisStatus.FAILED.value and not has_insights:
            logger.error(
                "master_analysis_failed",
                client_id=client_id,
                errors=errors,
            )
            # Continue to report with partial data
            return {
                "analysis_state": final_analysis_state,
                "current_phase": WorkflowPhase.REPORTING.value,
                "errors": errors,
            }

        logger.info(
            "master_analysis_complete",
            client_id=client_id,
            insights=len(final_analysis_state.get("insights", [])),
            recommendations=len(final_analysis_state.get("recommendations", [])),
        )

        return {
            "analysis_state": final_analysis_state,
            "current_phase": WorkflowPhase.REPORTING.value,
        }

    except Exception as e:
        logger.error("master_analysis_error", client_id=client_id, error=str(e))
        return {
            "errors": [f"Analysis phase error: {str(e)}"],
            "current_phase": WorkflowPhase.REPORTING.value,  # Try to continue
        }


async def run_report_phase(state: MasterState) -> dict:
    """Execute the report workflow phase.

    Generates HTML report and sends via email (if configured).

    Args:
        state: Current master state with analysis data.

    Returns:
        Partial state update with report results.
    """
    client_id = state.get("client_id", "unknown")
    analysis_state = state.get("analysis_state", {})
    collection_state = state.get("collection_state", {})

    logger.info("master_report_start", client_id=client_id)

    try:
        # Compile report graph
        report_graph = compile_report_graph()

        # Build analysis data for report
        analysis_data = {
            "sentiment_results": analysis_state.get("sentiment_results", {}),
            "theme_results": analysis_state.get("theme_results", []),
            "competitor_analysis": analysis_state.get("competitor_analysis", {}),
            "insights": analysis_state.get("insights", []),
            "recommendations": analysis_state.get("recommendations", []),
        }

        # Get business name
        business_name = (
            analysis_state.get("sentiment_results", {}).get("business_name")
            or collection_state.get("business_name", "Unknown")
        )

        # Create initial report state
        initial_state = create_report_state(
            business_id=client_id,
            analysis=analysis_data,
        )

        # Run report workflow
        final_report_state = await report_graph.ainvoke(initial_state)

        # Check status
        status = final_report_state.get("status", ReportStatus.FAILED.value)
        errors = final_report_state.get("errors", [])

        if status == ReportStatus.FAILED.value:
            # Retry once
            logger.warning("master_report_retry", client_id=client_id)
            final_report_state = await report_graph.ainvoke(initial_state)
            status = final_report_state.get("status", ReportStatus.FAILED.value)

            if status == ReportStatus.FAILED.value:
                logger.error(
                    "master_report_failed",
                    client_id=client_id,
                    errors=final_report_state.get("errors", []),
                )
                return {
                    "report_state": final_report_state,
                    "current_phase": WorkflowPhase.COMPLETE.value,
                    "errors": final_report_state.get("errors", []),
                }

        logger.info(
            "master_report_complete",
            client_id=client_id,
            html_length=len(final_report_state.get("report_html", "")),
            email_sent=final_report_state.get("email_sent", False),
        )

        return {
            "report_state": final_report_state,
            "current_phase": WorkflowPhase.COMPLETE.value,
        }

    except Exception as e:
        logger.error("master_report_error", client_id=client_id, error=str(e))
        return {
            "errors": [f"Report phase error: {str(e)}"],
            "current_phase": WorkflowPhase.COMPLETE.value,
        }


# =============================================================================
# Conditional Edge Functions
# =============================================================================


def should_continue_after_collection(
    state: MasterState,
) -> Literal["run_analysis_phase", "end"]:
    """Determine if pipeline should continue after collection.

    Args:
        state: Current master state.

    Returns:
        Next node or "end" if collection failed.
    """
    collection_state = state.get("collection_state", {})
    status = collection_state.get("status", CollectionStatus.FAILED.value)

    # Check if we have any data to analyze
    reviews = collection_state.get("reviews_collected", [])
    has_reviews = any(r.get("type") == "review" for r in reviews)

    if status == CollectionStatus.FAILED.value and not has_reviews:
        logger.warning("master_stopping_after_collection", reason="No data collected")
        return "end"

    return "run_analysis_phase"


def should_continue_after_analysis(
    state: MasterState,
) -> Literal["run_report_phase", "end"]:
    """Determine if pipeline should continue after analysis.

    Always continues to report phase, even with partial data.

    Args:
        state: Current master state.

    Returns:
        Always "run_report_phase" to generate report with available data.
    """
    # Always try to generate a report
    return "run_report_phase"


# =============================================================================
# Master Graph Builder
# =============================================================================


def create_master_graph() -> StateGraph:
    """Create the master orchestrator workflow graph.

    The graph chains:
    1. Collection Phase -> (conditional) ->
    2. Analysis Phase -> (always) ->
    3. Report Phase -> END

    Returns:
        StateGraph for master orchestration.
    """
    workflow = StateGraph(MasterState)

    # Add nodes
    workflow.add_node("run_collection_phase", run_collection_phase)
    workflow.add_node("run_analysis_phase", run_analysis_phase)
    workflow.add_node("run_report_phase", run_report_phase)

    # Set entry point
    workflow.set_entry_point("run_collection_phase")

    # Add conditional edge after collection
    workflow.add_conditional_edges(
        "run_collection_phase",
        should_continue_after_collection,
        {
            "run_analysis_phase": "run_analysis_phase",
            "end": END,
        },
    )

    # Add conditional edge after analysis (always continues)
    workflow.add_conditional_edges(
        "run_analysis_phase",
        should_continue_after_analysis,
        {
            "run_report_phase": "run_report_phase",
            "end": END,
        },
    )

    # Report phase goes to END
    workflow.add_edge("run_report_phase", END)

    return workflow


def compile_master_graph():
    """Create and compile the master graph.

    Returns:
        Compiled graph ready for invocation.
    """
    graph = create_master_graph()
    return graph.compile()


# =============================================================================
# Convenience Functions
# =============================================================================


async def run_full_pipeline(
    business_name: str,
    location: str = "",
    owner_email: Optional[str] = None,
) -> dict[str, Any]:
    """Run the complete LocalPulse pipeline for a business.

    This is the main entry point for processing a single business through
    the entire pipeline: Collection -> Analysis -> Report.

    Args:
        business_name: Name of the business to process.
        location: Optional location hint (e.g., "Manchester, UK").
        owner_email: Optional email address for report delivery.

    Returns:
        Dictionary containing:
        - success: Whether pipeline completed successfully
        - business_name: Name of the business
        - business_id: Generated unique ID
        - phase_completed: Last completed phase
        - collection_summary: Summary of collected data
        - analysis_summary: Summary of analysis results
        - report_summary: Summary of report generation
        - errors: List of any errors encountered
        - duration_seconds: Total pipeline duration
    """
    started_at = datetime.now(timezone.utc)
    client_id = str(uuid4())

    # Combine name and location
    full_name = f"{business_name} {location}".strip() if location else business_name

    logger.info(
        "pipeline_start",
        business_name=full_name,
        client_id=client_id,
    )

    result = PipelineResult(
        business_name=full_name,
        business_id=client_id,
        started_at=started_at,
    )

    try:
        # Create initial master state
        initial_state = create_master_state(
            client_id=client_id,
            business_name=full_name,
        )

        # Store email for later use (would be used in report phase)
        if owner_email:
            initial_state["report_state"]["owner_email"] = owner_email

        # Compile and run master graph
        master_graph = compile_master_graph()
        final_state = await master_graph.ainvoke(initial_state)

        # Extract results
        collection_state = final_state.get("collection_state", {})
        analysis_state = final_state.get("analysis_state", {})
        report_state = final_state.get("report_state", {})
        current_phase = final_state.get("current_phase", WorkflowPhase.COLLECTION.value)
        errors = final_state.get("errors", [])

        # Build collection summary
        reviews_collected = collection_state.get("reviews_collected", [])
        competitors_found = collection_state.get("competitors_found", [])
        result.collection_summary = {
            "status": collection_state.get("status", "unknown"),
            "google_place_id": collection_state.get("google_place_id"),
            "reviews_collected": len([r for r in reviews_collected if r.get("type") == "review"]),
            "competitors_found": len(competitors_found),
            "business_details": next(
                (r for r in reviews_collected if r.get("type") == "business_details"),
                {},
            ),
        }

        # Build analysis summary
        result.analysis_summary = {
            "status": analysis_state.get("status", "unknown"),
            "sentiment_score": analysis_state.get("sentiment_results", {}).get("overall_score"),
            "sentiment_trend": analysis_state.get("sentiment_results", {}).get("trend"),
            "insights_count": len(analysis_state.get("insights", [])),
            "recommendations_count": len(analysis_state.get("recommendations", [])),
            "market_position": analysis_state.get("competitor_analysis", {}).get("market_position"),
        }

        # Build report summary
        result.report_summary = {
            "status": report_state.get("status", "unknown"),
            "html_generated": len(report_state.get("report_html", "")) > 0,
            "html_length": len(report_state.get("report_html", "")),
            "email_sent": report_state.get("email_sent", False),
        }

        # Determine success
        result.phase_completed = current_phase
        result.success = current_phase == WorkflowPhase.COMPLETE.value
        result.errors = errors

    except Exception as e:
        logger.error("pipeline_error", error=str(e))
        result.errors.append(f"Pipeline error: {str(e)}")
        result.success = False

    result.completed_at = datetime.now(timezone.utc)

    logger.info(
        "pipeline_complete",
        business_name=full_name,
        success=result.success,
        duration_seconds=(result.completed_at - started_at).total_seconds(),
    )

    return result.to_dict()


async def run_batch_pipeline(
    clients: list[dict[str, Any]],
    delay_between: float = 2.0,
) -> list[dict[str, Any]]:
    """Run the pipeline for multiple clients in sequence.

    Processes each client one at a time with a configurable delay
    between each to respect API rate limits.

    Args:
        clients: List of client dictionaries, each containing:
            - business_name: Required business name
            - location: Optional location
            - owner_email: Optional email for report
        delay_between: Seconds to wait between clients (default 2.0)

    Returns:
        List of result dictionaries, one per client.

    Example:
        clients = [
            {"business_name": "Restaurant A", "location": "London"},
            {"business_name": "Restaurant B", "location": "Manchester"},
        ]
        results = await run_batch_pipeline(clients)
    """
    logger.info("batch_pipeline_start", client_count=len(clients))

    results = []

    for i, client in enumerate(clients):
        business_name = client.get("business_name", f"Unknown Client {i+1}")
        location = client.get("location", "")
        owner_email = client.get("owner_email")

        logger.info(
            "batch_processing_client",
            index=i + 1,
            total=len(clients),
            business_name=business_name,
        )

        try:
            result = await run_full_pipeline(
                business_name=business_name,
                location=location,
                owner_email=owner_email,
            )
            results.append(result)

        except Exception as e:
            logger.error(
                "batch_client_error",
                business_name=business_name,
                error=str(e),
            )
            results.append({
                "business_name": business_name,
                "success": False,
                "errors": [f"Batch processing error: {str(e)}"],
            })

        # Delay between clients (except for the last one)
        if i < len(clients) - 1 and delay_between > 0:
            logger.debug("batch_delay", seconds=delay_between)
            await asyncio.sleep(delay_between)

    # Summarize results
    successful = sum(1 for r in results if r.get("success", False))
    failed = len(results) - successful

    logger.info(
        "batch_pipeline_complete",
        total=len(results),
        successful=successful,
        failed=failed,
    )

    return results


# =============================================================================
# Test Functions
# =============================================================================


def _safe_print(text: str) -> None:
    """Print text safely, handling Unicode issues on Windows."""
    safe_text = text.encode("ascii", errors="replace").decode("ascii")
    print(safe_text)


async def test_master_workflow():
    """Test the master orchestrator with Circolo Popolare Manchester.

    Runs the full pipeline and prints progress at each phase.
    """
    _safe_print("=" * 70)
    _safe_print("Master Orchestrator Pipeline Test")
    _safe_print("=" * 70)

    business_name = "Circolo Popolare Manchester"

    _safe_print(f"\nStarting full pipeline for: {business_name}")
    _safe_print("-" * 70)

    # Create initial state
    client_id = str(uuid4())
    initial_state = create_master_state(
        client_id=client_id,
        business_name=business_name,
    )

    _safe_print(f"\nInitial State:")
    _safe_print(f"  Client ID: {client_id}")
    _safe_print(f"  Business Name: {business_name}")
    _safe_print(f"  Current Phase: {initial_state.get('current_phase')}")

    # Compile master graph
    master_graph = compile_master_graph()

    # Run with streaming to see progress
    _safe_print("\n" + "=" * 70)
    _safe_print("Pipeline Execution:")
    _safe_print("=" * 70)

    step_count = 0
    accumulated_state = dict(initial_state)

    async for event in master_graph.astream(initial_state):
        step_count += 1
        for node_name, node_state in event.items():
            # Merge updates
            for key, value in node_state.items():
                if key == "errors" and isinstance(value, list):
                    existing = accumulated_state.get(key, [])
                    accumulated_state[key] = existing + value
                else:
                    accumulated_state[key] = value

            _safe_print(f"\n[Phase {step_count}] {node_name.upper()}")
            _safe_print("=" * 50)

            if node_name == "run_collection_phase":
                collection = accumulated_state.get("collection_state", {})
                reviews = collection.get("reviews_collected", [])
                competitors = collection.get("competitors_found", [])

                _safe_print(f"  Status: {collection.get('status', 'N/A')}")
                _safe_print(f"  Google Place ID: {collection.get('google_place_id', 'N/A')}")
                _safe_print(f"  Reviews Collected: {len([r for r in reviews if r.get('type') == 'review'])}")
                _safe_print(f"  Competitors Found: {len(competitors)}")

                # Show business details
                details = next((r for r in reviews if r.get("type") == "business_details"), {})
                if details:
                    _safe_print(f"\n  Business Details:")
                    _safe_print(f"    Name: {details.get('name', 'N/A')}")
                    _safe_print(f"    Rating: {details.get('rating', 'N/A')}")
                    _safe_print(f"    Address: {details.get('address', 'N/A')[:50]}...")

            elif node_name == "run_analysis_phase":
                analysis = accumulated_state.get("analysis_state", {})
                sentiment = analysis.get("sentiment_results", {})
                insights = analysis.get("insights", [])
                recommendations = analysis.get("recommendations", [])

                _safe_print(f"  Status: {analysis.get('status', 'N/A')}")
                _safe_print(f"\n  Sentiment Analysis:")
                _safe_print(f"    Score: {sentiment.get('overall_score', 'N/A')}")
                _safe_print(f"    Trend: {sentiment.get('trend', 'N/A')}")
                _safe_print(f"    Positive: {sentiment.get('positive_count', 0)}")
                _safe_print(f"    Negative: {sentiment.get('negative_count', 0)}")

                _safe_print(f"\n  AI Analysis:")
                _safe_print(f"    Insights: {len(insights)}")
                _safe_print(f"    Recommendations: {len(recommendations)}")

                # Show top insight
                if insights:
                    _safe_print(f"\n  Top Insight:")
                    _safe_print(f"    {insights[0][:70]}...")

                # Show market position
                comp = analysis.get("competitor_analysis", {})
                _safe_print(f"\n  Market Position: {comp.get('market_position', 'N/A')}")

            elif node_name == "run_report_phase":
                report = accumulated_state.get("report_state", {})

                _safe_print(f"  Status: {report.get('status', 'N/A')}")
                _safe_print(f"  HTML Generated: {len(report.get('report_html', ''))} chars")
                _safe_print(f"  Email Sent: {report.get('email_sent', False)}")

    # Print final summary
    _safe_print("\n" + "=" * 70)
    _safe_print("Pipeline Summary:")
    _safe_print("=" * 70)

    final_phase = accumulated_state.get("current_phase", "unknown")
    errors = accumulated_state.get("errors", [])

    _safe_print(f"\n  Final Phase: {final_phase}")
    _safe_print(f"  Success: {final_phase == WorkflowPhase.COMPLETE.value}")

    collection = accumulated_state.get("collection_state", {})
    analysis = accumulated_state.get("analysis_state", {})
    report = accumulated_state.get("report_state", {})

    _safe_print(f"\n  Collection: {collection.get('status', 'N/A')}")
    _safe_print(f"  Analysis: {analysis.get('status', 'N/A')}")
    _safe_print(f"  Report: {report.get('status', 'N/A')}")

    if errors:
        _safe_print(f"\n  Errors ({len(errors)}):")
        for err in errors[:3]:
            _safe_print(f"    - {err[:60]}...")

    _safe_print("\n" + "=" * 70)
    _safe_print("Test completed!")
    _safe_print("=" * 70)

    return accumulated_state


async def test_convenience_function():
    """Test the run_full_pipeline convenience function."""
    _safe_print("=" * 70)
    _safe_print("Testing run_full_pipeline()")
    _safe_print("=" * 70)

    result = await run_full_pipeline(
        business_name="Circolo Popolare",
        location="Manchester",
    )

    _safe_print(f"\nResult:")
    _safe_print(f"  Success: {result.get('success')}")
    _safe_print(f"  Business: {result.get('business_name')}")
    _safe_print(f"  Phase Completed: {result.get('phase_completed')}")
    _safe_print(f"  Duration: {result.get('duration_seconds', 0):.1f} seconds")

    _safe_print(f"\n  Collection:")
    coll = result.get("collection_summary", {})
    _safe_print(f"    Status: {coll.get('status')}")
    _safe_print(f"    Reviews: {coll.get('reviews_collected')}")
    _safe_print(f"    Competitors: {coll.get('competitors_found')}")

    _safe_print(f"\n  Analysis:")
    analysis = result.get("analysis_summary", {})
    _safe_print(f"    Status: {analysis.get('status')}")
    _safe_print(f"    Sentiment: {analysis.get('sentiment_score')}")
    _safe_print(f"    Insights: {analysis.get('insights_count')}")

    _safe_print(f"\n  Report:")
    report = result.get("report_summary", {})
    _safe_print(f"    Status: {report.get('status')}")
    _safe_print(f"    HTML Generated: {report.get('html_generated')}")

    if result.get("errors"):
        _safe_print(f"\n  Errors: {result.get('errors')}")

    _safe_print("\n" + "=" * 70)

    return result


async def test_batch_pipeline():
    """Test the batch pipeline with multiple clients."""
    _safe_print("=" * 70)
    _safe_print("Testing run_batch_pipeline()")
    _safe_print("=" * 70)

    # Test with just one client for speed
    clients = [
        {"business_name": "Circolo Popolare", "location": "Manchester"},
    ]

    _safe_print(f"\nProcessing {len(clients)} client(s)...")

    results = await run_batch_pipeline(clients, delay_between=1.0)

    _safe_print(f"\nBatch Results:")
    for i, result in enumerate(results, 1):
        _safe_print(f"\n  Client {i}: {result.get('business_name')}")
        _safe_print(f"    Success: {result.get('success')}")
        _safe_print(f"    Duration: {result.get('duration_seconds', 0):.1f}s")

    successful = sum(1 for r in results if r.get("success"))
    _safe_print(f"\n  Total: {len(results)}, Successful: {successful}")

    _safe_print("\n" + "=" * 70)

    return results


if __name__ == "__main__":
    # Run the master workflow test
    asyncio.run(test_master_workflow())
