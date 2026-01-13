"""LangGraph workflow for AI-powered review analysis.

This module defines the analysis workflow that:
1. Fetches business and review data from Neo4j
2. Analyzes sentiment using Claude
3. Extracts recurring themes
4. Compares against competitors
5. Generates actionable insights
6. Creates specific recommendations

Uses Claude Haiku for cost-efficient analysis with structured outputs.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.graphs.state import AnalysisState, AnalysisStatus, create_analysis_state
from src.knowledge.neo4j_client import Neo4jClient

logger = structlog.get_logger(__name__)


# =============================================================================
# Pydantic Models for Structured Claude Outputs
# =============================================================================


class ReviewSentiment(BaseModel):
    """Sentiment analysis result for a single review."""

    review_id: str = Field(description="The review identifier")
    sentiment: Literal["positive", "negative", "neutral", "mixed"] = Field(
        description="Overall sentiment classification"
    )
    score: float = Field(
        description="Sentiment score from -1.0 (very negative) to 1.0 (very positive)",
        ge=-1.0,
        le=1.0,
    )
    confidence: float = Field(
        description="Confidence in the sentiment classification (0-1)",
        ge=0.0,
        le=1.0,
        default=0.8,
    )
    key_phrases: list[str] = Field(
        description="Key phrases that influenced the sentiment",
        default_factory=list,
    )


class SentimentAnalysisResult(BaseModel):
    """Aggregated sentiment analysis results."""

    reviews: list[ReviewSentiment] = Field(
        description="Sentiment analysis for each review"
    )
    overall_score: float = Field(
        description="Average sentiment score across all reviews",
        ge=-1.0,
        le=1.0,
    )
    positive_count: int = Field(description="Number of positive reviews")
    negative_count: int = Field(description="Number of negative reviews")
    neutral_count: int = Field(description="Number of neutral reviews")
    trend: Literal["improving", "declining", "stable"] = Field(
        description="Overall sentiment trend based on review dates"
    )
    summary: str = Field(description="Brief summary of the sentiment analysis")


class Theme(BaseModel):
    """A recurring theme identified in reviews."""

    name: str = Field(description="Theme name (e.g., 'Food Quality', 'Service Speed')")
    category: Literal[
        "food_quality",
        "service",
        "ambiance",
        "value",
        "cleanliness",
        "location",
        "menu",
        "staff",
        "wait_time",
        "other",
    ] = Field(description="Theme category", default="other")
    mention_count: int = Field(description="Number of reviews mentioning this theme", default=1)
    average_sentiment: float = Field(
        description="Average sentiment when this theme is mentioned",
        ge=-1.0,
        le=1.0,
        default=0.0,
    )
    is_strength: bool = Field(
        description="Whether this theme is a strength (positive) or weakness (negative)",
        default=True,
    )
    example_quotes: list[str] = Field(
        description="Example quotes from reviews mentioning this theme",
        default_factory=list,
    )


class ThemeAnalysisResult(BaseModel):
    """Theme extraction results."""

    themes: list[Theme] = Field(description="List of identified themes", default_factory=list)
    top_strengths: list[str] = Field(
        description="Top 3 strengths based on positive themes",
        default_factory=list,
    )
    top_weaknesses: list[str] = Field(
        description="Top 3 areas for improvement based on negative themes",
        default_factory=list,
    )
    summary: str = Field(description="Brief summary of theme analysis", default="")


class CompetitorComparison(BaseModel):
    """Comparison with a single competitor."""

    competitor_name: str = Field(description="Name of the competitor")
    rating_difference: float = Field(
        description="Rating difference (positive means client is higher)",
        default=0.0,
    )
    strengths_vs_competitor: list[str] = Field(
        description="Areas where client outperforms this competitor",
        default_factory=list,
    )
    weaknesses_vs_competitor: list[str] = Field(
        description="Areas where competitor outperforms client",
        default_factory=list,
    )


class CompetitorAnalysisResult(BaseModel):
    """Comparative analysis against competitors."""

    comparisons: list[CompetitorComparison] = Field(
        description="Comparison with each competitor",
        default_factory=list,
    )
    market_position: Literal["leader", "competitive", "lagging", "unknown"] = Field(
        description="Overall market position relative to competitors",
        default="competitive",
    )
    competitive_advantages: list[str] = Field(
        description="Key competitive advantages",
        default_factory=list,
    )
    competitive_gaps: list[str] = Field(
        description="Areas where competitors have an edge",
        default_factory=list,
    )
    summary: str = Field(description="Brief summary of competitive position", default="")


class Insight(BaseModel):
    """A single actionable insight."""

    title: str = Field(description="Short insight title")
    description: str = Field(description="Detailed insight explanation")
    impact: Literal["high", "medium", "low"] = Field(
        description="Potential impact if addressed"
    )
    category: Literal[
        "opportunity", "risk", "trend", "competitive", "operational"
    ] = Field(description="Type of insight")
    supporting_data: list[str] = Field(
        description="Data points supporting this insight"
    )


class InsightsResult(BaseModel):
    """Generated insights from analysis."""

    insights: list[Insight] = Field(description="List of insights")
    executive_summary: str = Field(
        description="Executive summary of all insights (2-3 sentences)"
    )


class Recommendation(BaseModel):
    """A specific recommendation for the business owner."""

    title: str = Field(description="Short recommendation title")
    description: str = Field(description="Detailed recommendation")
    priority: Literal["high", "medium", "low"] = Field(
        description="Implementation priority"
    )
    category: Literal[
        "service", "menu", "marketing", "operations", "staff", "ambiance", "value"
    ] = Field(description="Recommendation category")
    expected_outcome: str = Field(
        description="Expected outcome if implemented"
    )
    implementation_steps: list[str] = Field(
        description="Concrete steps to implement this recommendation"
    )


class RecommendationsResult(BaseModel):
    """Generated recommendations."""

    recommendations: list[Recommendation] = Field(
        description="List of recommendations"
    )
    quick_wins: list[str] = Field(
        description="Recommendations that can be implemented immediately"
    )
    strategic_initiatives: list[str] = Field(
        description="Longer-term strategic recommendations"
    )


# =============================================================================
# Prompt Templates
# =============================================================================


SENTIMENT_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert hospitality industry analyst specializing in customer sentiment analysis.
Your task is to analyze restaurant reviews and determine the sentiment of each review.

Guidelines:
- Consider the overall tone, specific praise or complaints, and emotional language
- A score of 1.0 means extremely positive, -1.0 means extremely negative, 0 is neutral
- Look for nuance - a review can mention both positives and negatives
- Identify key phrases that drive the sentiment
- Assess the trend based on review dates if available (most recent reviews indicate current direction)

Be objective and precise in your analysis.""",
    ),
    (
        "human",
        """Analyze the sentiment of the following reviews for {business_name}:

{reviews_text}

Provide a comprehensive sentiment analysis including:
1. Individual sentiment for each review with scores and key phrases
2. Overall aggregated sentiment score
3. Counts of positive, negative, and neutral reviews
4. Whether sentiment is improving, declining, or stable
5. A brief summary of the findings""",
    ),
])


THEME_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert hospitality industry analyst specializing in identifying customer experience themes.
Your task is to extract recurring themes from restaurant reviews.

Common theme categories in hospitality:
- food_quality: Taste, freshness, presentation, portion sizes
- service: Staff attentiveness, friendliness, professionalism
- ambiance: Atmosphere, decor, noise level, comfort
- value: Price-to-quality ratio, value for money
- cleanliness: Hygiene, tidiness of venue
- location: Accessibility, parking, neighborhood
- menu: Variety, dietary options, seasonal offerings
- staff: Individual staff members, management
- wait_time: Speed of service, reservations, queues

Identify both strengths (positive themes) and weaknesses (negative themes).
Include specific quotes as evidence.""",
    ),
    (
        "human",
        """Extract themes from the following reviews for {business_name}:

{reviews_text}

Identify:
1. All recurring themes with mention counts and sentiment
2. Which themes are strengths vs weaknesses
3. Example quotes for each theme
4. Top 3 strengths and top 3 areas for improvement""",
    ),
])


COMPETITOR_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert hospitality industry analyst specializing in competitive intelligence.
Your task is to compare a restaurant's performance against its competitors.

Focus on:
- Rating comparisons (quantitative)
- Qualitative differences in customer feedback themes
- Unique selling points and competitive advantages
- Areas where competitors excel

Be specific and actionable in your comparisons.""",
    ),
    (
        "human",
        """Compare {business_name} against its competitors:

Client Business:
- Name: {business_name}
- Rating: {client_rating}
- Key Themes: {client_themes}
- Review Summary: {client_summary}

Competitors:
{competitors_text}

Provide:
1. Detailed comparison with each competitor
2. Overall market position assessment
3. Key competitive advantages
4. Areas where competitors have an edge""",
    ),
])


INSIGHTS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a senior hospitality consultant generating actionable business insights.
Your task is to synthesize analysis results into clear, impactful insights.

Insight categories:
- opportunity: Untapped potential or market gaps
- risk: Issues that could harm the business if not addressed
- trend: Emerging patterns in customer behavior or preferences
- competitive: Insights about competitive positioning
- operational: Efficiency or process-related insights

Each insight should be:
- Specific and data-driven
- Actionable for a restaurant owner
- Prioritized by potential impact""",
    ),
    (
        "human",
        """Generate insights for {business_name} based on this analysis:

Sentiment Analysis:
{sentiment_summary}

Theme Analysis:
{theme_summary}

Competitive Position:
{competitor_summary}

Generate 5-7 key insights with:
1. Clear titles and descriptions
2. Impact assessment (high/medium/low)
3. Supporting data points
4. An executive summary""",
    ),
])


RECOMMENDATIONS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a hospitality business consultant creating actionable recommendations.
Your task is to convert insights into specific, implementable recommendations.

Recommendation categories:
- service: Customer service improvements
- menu: Menu changes or additions
- marketing: Promotional or branding activities
- operations: Process and efficiency improvements
- staff: Training or staffing recommendations
- ambiance: Atmosphere or decor changes
- value: Pricing or value proposition adjustments

Each recommendation should include:
- Concrete implementation steps
- Expected outcomes
- Priority level based on impact and effort""",
    ),
    (
        "human",
        """Create recommendations for {business_name} based on these insights:

Key Insights:
{insights_text}

Strengths to Leverage:
{strengths}

Weaknesses to Address:
{weaknesses}

Generate 5-8 specific recommendations including:
1. High-priority quick wins (can implement this week)
2. Medium-term improvements (1-3 months)
3. Strategic initiatives (3+ months)

For each recommendation, provide clear implementation steps.""",
    ),
])


# =============================================================================
# Node Functions
# =============================================================================


def _get_llm() -> ChatAnthropic:
    """Get configured Claude Haiku instance."""
    settings = get_settings()
    api_key = settings.anthropic_api_key
    if api_key:
        api_key = api_key.get_secret_value()

    return ChatAnthropic(
        model="claude-3-haiku-20240307",
        api_key=api_key,
        temperature=0.3,
        max_tokens=4096,
    )


async def fetch_data(state: AnalysisState) -> dict:
    """Fetch business and review data from Neo4j.

    Args:
        state: Current analysis state with business_id.

    Returns:
        Partial state update with business data and reviews.
    """
    business_id = state.get("business_id")
    logger.info("analysis_fetch_data", business_id=business_id)

    try:
        async with Neo4jClient() as client:
            # Fetch business details
            business_query = """
            MATCH (b:Business)
            WHERE b.id = $business_id OR b.google_place_id = $business_id
            OPTIONAL MATCH (b)-[:HAS_REVIEW]->(r:Review)
            OPTIONAL MATCH (b)-[:COMPETES_WITH]->(c:Business)
            RETURN b AS business,
                   collect(DISTINCT r) AS reviews,
                   collect(DISTINCT c) AS competitors
            """

            results = await client.run_query(
                business_query,
                {"business_id": business_id},
            )

            if not results or not results[0].get("business"):
                # Try to find by name pattern
                name_query = """
                MATCH (b:Business)
                WHERE b.name CONTAINS $search_term
                OPTIONAL MATCH (b)-[:HAS_REVIEW]->(r:Review)
                OPTIONAL MATCH (b)-[:COMPETES_WITH]->(c:Business)
                RETURN b AS business,
                       collect(DISTINCT r) AS reviews,
                       collect(DISTINCT c) AS competitors
                LIMIT 1
                """
                results = await client.run_query(
                    name_query,
                    {"search_term": business_id},
                )

            if not results or not results[0].get("business"):
                return {
                    "errors": [f"Business not found: {business_id}"],
                    "status": AnalysisStatus.FAILED.value,
                }

            result = results[0]
            business = dict(result["business"])
            reviews = [dict(r) for r in result["reviews"] if r]
            competitors = [dict(c) for c in result["competitors"] if c]

            logger.info(
                "analysis_data_fetched",
                business_name=business.get("name"),
                review_count=len(reviews),
                competitor_count=len(competitors),
            )

            return {
                "business_id": business.get("id") or business.get("google_place_id"),
                "reviews": reviews,
                "sentiment_results": {
                    "business_name": business.get("name"),
                    "business_rating": business.get("rating"),
                    "review_count": len(reviews),
                },
                "competitor_analysis": {
                    "competitors": competitors,
                    "business_name": business.get("name"),
                    "business_rating": business.get("rating"),
                },
                "status": AnalysisStatus.ANALYZING.value,
            }

    except Exception as e:
        logger.error("analysis_fetch_failed", error=str(e))
        return {
            "errors": [f"Data fetch failed: {str(e)}"],
            "status": AnalysisStatus.FAILED.value,
        }


async def analyze_sentiment(state: AnalysisState) -> dict:
    """Analyze sentiment of reviews using Claude.

    Args:
        state: Current state with reviews.

    Returns:
        Partial state update with sentiment results.
    """
    reviews = state.get("reviews", [])
    business_name = state.get("sentiment_results", {}).get("business_name", "Unknown")

    if not reviews:
        logger.info("analysis_no_reviews_for_sentiment")
        return {
            "sentiment_results": {
                **state.get("sentiment_results", {}),
                "overall_score": 0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "trend": "stable",
                "summary": "No reviews available for sentiment analysis.",
            }
        }

    logger.info("analysis_sentiment_start", review_count=len(reviews))

    try:
        # Format reviews for the prompt
        reviews_text = "\n\n".join([
            f"Review {i+1} (ID: {r.get('id', f'review_{i}')}, Rating: {r.get('rating', 'N/A')}/5):\n\"{r.get('text', 'No text')}\""
            for i, r in enumerate(reviews)
        ])

        llm = _get_llm()
        structured_llm = llm.with_structured_output(SentimentAnalysisResult)

        prompt = SENTIMENT_ANALYSIS_PROMPT.format(
            business_name=business_name,
            reviews_text=reviews_text,
        )

        result: SentimentAnalysisResult = await structured_llm.ainvoke(prompt)

        logger.info(
            "analysis_sentiment_complete",
            overall_score=result.overall_score,
            positive=result.positive_count,
            negative=result.negative_count,
        )

        return {
            "sentiment_results": {
                **state.get("sentiment_results", {}),
                "overall_score": result.overall_score,
                "positive_count": result.positive_count,
                "negative_count": result.negative_count,
                "neutral_count": result.neutral_count,
                "trend": result.trend,
                "summary": result.summary,
                "review_sentiments": [r.model_dump() for r in result.reviews],
            }
        }

    except Exception as e:
        logger.error("analysis_sentiment_failed", error=str(e))
        return {
            "errors": [f"Sentiment analysis failed: {str(e)}"],
        }


async def extract_themes(state: AnalysisState) -> dict:
    """Extract recurring themes from reviews using Claude.

    Args:
        state: Current state with reviews.

    Returns:
        Partial state update with theme results.
    """
    reviews = state.get("reviews", [])
    business_name = state.get("sentiment_results", {}).get("business_name", "Unknown")

    if not reviews:
        logger.info("analysis_no_reviews_for_themes")
        return {
            "theme_results": [{
                "summary": "No reviews available for theme extraction.",
                "themes": [],
                "top_strengths": [],
                "top_weaknesses": [],
            }]
        }

    logger.info("analysis_themes_start", review_count=len(reviews))

    try:
        # Format reviews for the prompt
        reviews_text = "\n\n".join([
            f"Review {i+1} (Rating: {r.get('rating', 'N/A')}/5):\n\"{r.get('text', 'No text')}\""
            for i, r in enumerate(reviews)
        ])

        llm = _get_llm()
        structured_llm = llm.with_structured_output(ThemeAnalysisResult)

        prompt = THEME_EXTRACTION_PROMPT.format(
            business_name=business_name,
            reviews_text=reviews_text,
        )

        result: ThemeAnalysisResult = await structured_llm.ainvoke(prompt)

        logger.info(
            "analysis_themes_complete",
            theme_count=len(result.themes),
            strengths=len(result.top_strengths),
            weaknesses=len(result.top_weaknesses),
        )

        return {
            "theme_results": [{
                "summary": result.summary,
                "themes": [t.model_dump() for t in result.themes],
                "top_strengths": result.top_strengths,
                "top_weaknesses": result.top_weaknesses,
            }]
        }

    except Exception as e:
        logger.error("analysis_themes_failed", error=str(e))
        return {
            "errors": [f"Theme extraction failed: {str(e)}"],
        }


async def compare_competitors(state: AnalysisState) -> dict:
    """Compare client against competitors using Claude.

    Args:
        state: Current state with competitor data.

    Returns:
        Partial state update with competitor analysis.
    """
    competitor_data = state.get("competitor_analysis", {})
    competitors = competitor_data.get("competitors", [])
    business_name = competitor_data.get("business_name", "Unknown")
    client_rating = competitor_data.get("business_rating", 0)

    if not competitors:
        logger.info("analysis_no_competitors")
        return {
            "competitor_analysis": {
                **competitor_data,
                "market_position": "unknown",
                "competitive_advantages": [],
                "competitive_gaps": [],
                "comparisons": [],
                "summary": "No competitor data available for comparison.",
            }
        }

    logger.info("analysis_competitors_start", competitor_count=len(competitors))

    try:
        # Get theme data for context
        theme_results = state.get("theme_results", [])
        client_themes = []
        if theme_results:
            themes_data = theme_results[0] if isinstance(theme_results, list) else theme_results
            client_themes = themes_data.get("top_strengths", []) + themes_data.get("top_weaknesses", [])

        sentiment_summary = state.get("sentiment_results", {}).get("summary", "No sentiment data")

        # Format competitors
        competitors_text = "\n\n".join([
            f"Competitor: {c.get('name', 'Unknown')}\n"
            f"- Rating: {c.get('rating', 'N/A')}\n"
            f"- Address: {c.get('address', 'N/A')}\n"
            f"- Type: {c.get('primary_type', 'N/A')}"
            for c in competitors[:10]  # Limit to top 10
        ])

        llm = _get_llm()
        structured_llm = llm.with_structured_output(CompetitorAnalysisResult)

        prompt = COMPETITOR_ANALYSIS_PROMPT.format(
            business_name=business_name,
            client_rating=client_rating,
            client_themes=", ".join(client_themes[:5]) if client_themes else "Not analyzed yet",
            client_summary=sentiment_summary,
            competitors_text=competitors_text,
        )

        result: CompetitorAnalysisResult = await structured_llm.ainvoke(prompt)

        logger.info(
            "analysis_competitors_complete",
            market_position=result.market_position,
            advantages=len(result.competitive_advantages),
        )

        return {
            "competitor_analysis": {
                **competitor_data,
                "market_position": result.market_position,
                "competitive_advantages": result.competitive_advantages,
                "competitive_gaps": result.competitive_gaps,
                "comparisons": [c.model_dump() for c in result.comparisons],
                "summary": result.summary,
            }
        }

    except Exception as e:
        logger.error("analysis_competitors_failed", error=str(e))
        return {
            "errors": [f"Competitor analysis failed: {str(e)}"],
        }


async def generate_insights(state: AnalysisState) -> dict:
    """Generate actionable insights using Claude.

    Args:
        state: Current state with all analysis results.

    Returns:
        Partial state update with insights.
    """
    business_name = state.get("sentiment_results", {}).get("business_name", "Unknown")

    logger.info("analysis_insights_start", business_name=business_name)

    try:
        sentiment_results = state.get("sentiment_results", {})
        theme_results = state.get("theme_results", [])
        competitor_analysis = state.get("competitor_analysis", {})

        sentiment_summary = sentiment_results.get("summary", "No sentiment analysis available")
        theme_data = theme_results[0] if theme_results else {}
        theme_summary = theme_data.get("summary", "No theme analysis available")
        competitor_summary = competitor_analysis.get("summary", "No competitor analysis available")

        llm = _get_llm()
        structured_llm = llm.with_structured_output(InsightsResult)

        prompt = INSIGHTS_PROMPT.format(
            business_name=business_name,
            sentiment_summary=sentiment_summary,
            theme_summary=theme_summary,
            competitor_summary=competitor_summary,
        )

        result: InsightsResult = await structured_llm.ainvoke(prompt)

        logger.info(
            "analysis_insights_complete",
            insight_count=len(result.insights),
        )

        # Convert insights to list of strings for state
        insights_list = [
            f"[{i.impact.upper()}] {i.title}: {i.description}"
            for i in result.insights
        ]

        return {
            "insights": insights_list,
            "sentiment_results": {
                **sentiment_results,
                "executive_summary": result.executive_summary,
                "detailed_insights": [i.model_dump() for i in result.insights],
            }
        }

    except Exception as e:
        logger.error("analysis_insights_failed", error=str(e))
        return {
            "errors": [f"Insight generation failed: {str(e)}"],
        }


async def generate_recommendations(state: AnalysisState) -> dict:
    """Generate specific recommendations using Claude.

    Args:
        state: Current state with insights.

    Returns:
        Partial state update with recommendations and final status.
    """
    business_name = state.get("sentiment_results", {}).get("business_name", "Unknown")

    logger.info("analysis_recommendations_start", business_name=business_name)

    try:
        theme_results = state.get("theme_results", [])
        theme_data = theme_results[0] if theme_results else {}
        strengths = theme_data.get("top_strengths", [])
        weaknesses = theme_data.get("top_weaknesses", [])

        insights = state.get("insights", [])
        insights_text = "\n".join([f"- {insight}" for insight in insights])

        llm = _get_llm()
        structured_llm = llm.with_structured_output(RecommendationsResult)

        prompt = RECOMMENDATIONS_PROMPT.format(
            business_name=business_name,
            insights_text=insights_text or "No insights available",
            strengths=", ".join(strengths) if strengths else "Not identified",
            weaknesses=", ".join(weaknesses) if weaknesses else "Not identified",
        )

        result: RecommendationsResult = await structured_llm.ainvoke(prompt)

        logger.info(
            "analysis_recommendations_complete",
            recommendation_count=len(result.recommendations),
            quick_wins=len(result.quick_wins),
        )

        # Convert recommendations to list of strings for state
        recommendations_list = [
            f"[{r.priority.upper()}] {r.title}: {r.description}"
            for r in result.recommendations
        ]

        return {
            "recommendations": recommendations_list,
            "sentiment_results": {
                **state.get("sentiment_results", {}),
                "detailed_recommendations": [r.model_dump() for r in result.recommendations],
                "quick_wins": result.quick_wins,
                "strategic_initiatives": result.strategic_initiatives,
            },
            "status": AnalysisStatus.COMPLETED.value,
        }

    except Exception as e:
        logger.error("analysis_recommendations_failed", error=str(e))
        return {
            "errors": [f"Recommendation generation failed: {str(e)}"],
            "status": AnalysisStatus.COMPLETED.value,  # Mark complete even with errors
        }


# =============================================================================
# Graph Builder
# =============================================================================


def create_analysis_graph() -> StateGraph:
    """Create the analysis workflow graph.

    The graph executes the following flow:
    1. fetch_data - Get business and reviews from Neo4j
    2. analyze_sentiment - Claude analyzes sentiment
    3. extract_themes - Claude extracts themes
    4. compare_competitors - Claude compares against competitors
    5. generate_insights - Claude generates insights
    6. generate_recommendations - Claude creates action items

    Returns:
        StateGraph for analysis workflow.
    """
    workflow = StateGraph(AnalysisState)

    # Add nodes
    workflow.add_node("fetch_data", fetch_data)
    workflow.add_node("analyze_sentiment", analyze_sentiment)
    workflow.add_node("extract_themes", extract_themes)
    workflow.add_node("compare_competitors", compare_competitors)
    workflow.add_node("generate_insights", generate_insights)
    workflow.add_node("generate_recommendations", generate_recommendations)

    # Set entry point
    workflow.set_entry_point("fetch_data")

    # Add sequential edges
    workflow.add_edge("fetch_data", "analyze_sentiment")
    workflow.add_edge("analyze_sentiment", "extract_themes")
    workflow.add_edge("extract_themes", "compare_competitors")
    workflow.add_edge("compare_competitors", "generate_insights")
    workflow.add_edge("generate_insights", "generate_recommendations")
    workflow.add_edge("generate_recommendations", END)

    return workflow


def compile_analysis_graph():
    """Create and compile the analysis graph.

    Returns:
        Compiled graph ready for invocation.
    """
    graph = create_analysis_graph()
    return graph.compile()


# =============================================================================
# Convenience Function
# =============================================================================


async def run_analysis(business_id: str) -> AnalysisState:
    """Run the analysis workflow for a business.

    Args:
        business_id: Business ID or name to analyze.

    Returns:
        Final AnalysisState with all analysis results.
    """
    initial_state = create_analysis_state(business_id=business_id)

    graph = compile_analysis_graph()
    final_state = await graph.ainvoke(initial_state)

    return final_state


# =============================================================================
# Test Function
# =============================================================================


def _safe_print(text: str) -> None:
    """Print text safely, handling Unicode issues on Windows."""
    safe_text = text.encode("ascii", errors="replace").decode("ascii")
    print(safe_text)


async def test_analysis_workflow():
    """Test the analysis workflow with Circolo Popolare Manchester.

    Fetches data from Neo4j and runs full AI analysis.
    """
    _safe_print("=" * 70)
    _safe_print("Analysis Workflow Test")
    _safe_print("=" * 70)

    business_name = "Circolo Popolare"

    _safe_print(f"\nStarting analysis for: {business_name}")
    _safe_print("-" * 70)

    # Create initial state
    initial_state = create_analysis_state(business_id=business_name)

    _safe_print(f"\nInitial State:")
    _safe_print(f"  Business ID: {business_name}")
    _safe_print(f"  Status: {initial_state.get('status')}")

    # Compile the graph
    graph = compile_analysis_graph()

    # Run with streaming
    _safe_print("\n" + "=" * 70)
    _safe_print("Workflow Execution:")
    _safe_print("=" * 70)

    step_count = 0
    accumulated_state = dict(initial_state)

    async for event in graph.astream(initial_state):
        step_count += 1
        for node_name, node_state in event.items():
            # Merge updates into accumulated state
            for key, value in node_state.items():
                if key in ["insights", "recommendations", "theme_results", "errors"] and isinstance(value, list):
                    existing = accumulated_state.get(key, [])
                    accumulated_state[key] = existing + value
                else:
                    accumulated_state[key] = value

            _safe_print(f"\n[Step {step_count}] {node_name}")
            _safe_print("-" * 40)

            if node_name == "fetch_data":
                reviews = accumulated_state.get("reviews", [])
                competitors = accumulated_state.get("competitor_analysis", {}).get("competitors", [])
                business = accumulated_state.get("sentiment_results", {}).get("business_name")
                _safe_print(f"  Business: {business}")
                _safe_print(f"  Reviews found: {len(reviews)}")
                _safe_print(f"  Competitors found: {len(competitors)}")

            elif node_name == "analyze_sentiment":
                sentiment = accumulated_state.get("sentiment_results", {})
                _safe_print(f"  Overall Score: {sentiment.get('overall_score', 'N/A')}")
                _safe_print(f"  Positive: {sentiment.get('positive_count', 0)}")
                _safe_print(f"  Negative: {sentiment.get('negative_count', 0)}")
                _safe_print(f"  Neutral: {sentiment.get('neutral_count', 0)}")
                _safe_print(f"  Trend: {sentiment.get('trend', 'N/A')}")
                _safe_print(f"  Summary: {sentiment.get('summary', 'N/A')[:100]}...")

            elif node_name == "extract_themes":
                theme_results = accumulated_state.get("theme_results", [])
                if theme_results:
                    theme_data = theme_results[0] if isinstance(theme_results, list) else theme_results
                    themes = theme_data.get("themes", [])
                    _safe_print(f"  Themes identified: {len(themes)}")
                    _safe_print(f"  Top Strengths: {theme_data.get('top_strengths', [])}")
                    _safe_print(f"  Top Weaknesses: {theme_data.get('top_weaknesses', [])}")

            elif node_name == "compare_competitors":
                comp_analysis = accumulated_state.get("competitor_analysis", {})
                _safe_print(f"  Market Position: {comp_analysis.get('market_position', 'N/A')}")
                _safe_print(f"  Advantages: {comp_analysis.get('competitive_advantages', [])[:3]}")
                _safe_print(f"  Gaps: {comp_analysis.get('competitive_gaps', [])[:3]}")

            elif node_name == "generate_insights":
                insights = accumulated_state.get("insights", [])
                _safe_print(f"  Insights generated: {len(insights)}")
                for i, insight in enumerate(insights[:3], 1):
                    _safe_print(f"    {i}. {insight[:80]}...")

            elif node_name == "generate_recommendations":
                recommendations = accumulated_state.get("recommendations", [])
                _safe_print(f"  Recommendations generated: {len(recommendations)}")
                for i, rec in enumerate(recommendations[:3], 1):
                    _safe_print(f"    {i}. {rec[:80]}...")

    # Print final summary
    _safe_print("\n" + "=" * 70)
    _safe_print("Final Analysis Summary:")
    _safe_print("=" * 70)

    sentiment = accumulated_state.get("sentiment_results", {})
    _safe_print(f"\n  Business: {sentiment.get('business_name', 'Unknown')}")
    _safe_print(f"  Status: {accumulated_state.get('status')}")

    _safe_print(f"\n  SENTIMENT:")
    _safe_print(f"    Score: {sentiment.get('overall_score', 'N/A')}")
    _safe_print(f"    Trend: {sentiment.get('trend', 'N/A')}")
    exec_summary = sentiment.get("executive_summary", "N/A")
    _safe_print(f"    Executive Summary: {exec_summary[:150] if exec_summary else 'N/A'}...")

    _safe_print(f"\n  INSIGHTS ({len(accumulated_state.get('insights', []))}):")
    for insight in accumulated_state.get("insights", [])[:5]:
        _safe_print(f"    - {insight[:70]}...")

    _safe_print(f"\n  RECOMMENDATIONS ({len(accumulated_state.get('recommendations', []))}):")
    for rec in accumulated_state.get("recommendations", [])[:5]:
        _safe_print(f"    - {rec[:70]}...")

    # Quick wins
    quick_wins = sentiment.get("quick_wins", [])
    if quick_wins:
        _safe_print(f"\n  QUICK WINS:")
        for qw in quick_wins[:3]:
            _safe_print(f"    - {qw[:70]}...")

    if accumulated_state.get("errors"):
        _safe_print(f"\n  ERRORS: {accumulated_state.get('errors')}")

    _safe_print("\n" + "=" * 70)
    _safe_print("Test completed!")
    _safe_print("=" * 70)

    return accumulated_state


if __name__ == "__main__":
    asyncio.run(test_analysis_workflow())
