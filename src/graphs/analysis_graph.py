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
        default=0.0,
    )
    confidence: float = Field(
        description="Confidence in the sentiment classification (0-1)",
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
        description="Average sentiment score across all reviews (-1.0 to 1.0 scale)",
        default=0.0,
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

    name: str = Field(description="Theme name (e.g., 'Friendly Staff', 'Wait Times', 'Product Quality')")
    category: Literal[
        "product_quality",
        "service",
        "environment",
        "value",
        "cleanliness",
        "location",
        "offerings",
        "staff",
        "wait_time",
        "other",
    ] = Field(description="Theme category", default="other")
    mention_count: int = Field(description="Number of reviews mentioning this theme", default=1)
    average_sentiment: float = Field(
        description="Average sentiment when this theme is mentioned (-1.0 to 1.0 scale)",
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
    competitor_rating: Optional[float] = Field(
        description="The competitor's star rating",
        default=None,
    )
    rating_difference: Optional[float] = Field(
        description="Rating difference (positive means client is higher)",
        default=0.0,
    )
    strengths_vs_competitor: list[str] = Field(
        description="Specific areas where client outperforms this competitor",
        default_factory=list,
    )
    weaknesses_vs_competitor: list[str] = Field(
        description="Specific areas where competitor outperforms client",
        default_factory=list,
    )
    opportunity: str = Field(
        description="One specific opportunity the client can exploit based on this competitor's weaknesses",
        default="",
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
        "service", "offerings", "marketing", "operations", "staff", "environment", "value"
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
        """You are an expert business review analyst. Analyze customer reviews with precision for any type of business.

Rules:
- Score each review from -1.0 (very negative) to 1.0 (very positive)
- Extract the SPECIFIC phrases from each review that drive sentiment (not generic descriptions - use the reviewer's actual words)
- For the trend, compare sentiment of newer vs older reviews if dates are available
- A "mixed" review praises some things and criticizes others - score it based on the overall weight
- Be precise: quote the exact words from the review, e.g. "friendly pharmacist" or "best haircut ever", not generic labels like "good service".""",
    ),
    (
        "human",
        """Analyze sentiment for these {review_count} reviews of {business_name}:

{reviews_text}

For each review: sentiment label, score, and the specific phrases (quoted from the review) that drive the sentiment.
Then: overall score, counts by category, trend direction, and a 2-sentence summary.""",
    ),
])


THEME_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert business review analyst extracting SPECIFIC themes from customer reviews. This could be any type of business — adapt to whatever the reviews describe.

CRITICAL: Be specific, not generic.
- BAD: "Product Quality" mentioned 5 times
- GOOD: "Consultation process" mentioned in 12 of 30 reviews, "Friendly reception staff" in 7, "Parking availability" in 6

Rules:
1. Name themes by the SPECIFIC product, service, staff member role, or issue mentioned - not generic categories
2. Count EXACTLY how many reviews mention each theme out of the total
3. For each theme, pull 2-3 DIRECT QUOTES from the actual reviews (copy the reviewer's words exactly)
4. IMPORTANT: You MUST only use English-language quotes in example_quotes. If the only reviews mentioning a theme are in a non-English language, write "No English quotes available" instead of quoting the non-English text. NEVER include non-English text in quotes.
5. Calculate per-theme sentiment: a business can have great product sentiment but terrible wait time sentiment
6. Flag any EMERGING themes that appear only in the most recent reviews but not older ones
7. Categories are for grouping only - the theme NAME must be specific (e.g., "Weekend appointment availability" not "wait_time")

Theme categories for grouping: product_quality, service, environment, value, cleanliness, location, offerings, staff, wait_time, other.""",
    ),
    (
        "human",
        """Extract specific themes from these {review_count} reviews of {business_name}:

{reviews_text}

For each theme found:
- Specific name (the actual product, service aspect, or issue)
- Category for grouping
- Exact mention count out of {review_count} reviews
- Per-theme sentiment score
- Whether it's a strength or weakness
- 2-3 direct quotes from reviewers (copy their exact words, English only)

Then list top 3 specific strengths and top 3 specific areas needing improvement.
Write a 2-sentence summary focused on what makes this business distinctive.""",
    ),
])


COMPETITOR_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert business analyst producing NAMED competitive intelligence. This could be any type of business — adapt to whatever industry the data describes.

CRITICAL: Name every competitor explicitly and compare with specifics.
- BAD: "Competitors tend to have better service"
- GOOD: "Sunrise Pharmacy (4.3 stars): customers praise their quick prescription turnaround and knowledgeable staff, but complain about limited parking."

ANTI-HALLUCINATION RULES:
- NEVER invent or fabricate statistics, percentages, or specific numbers that are not directly stated in the reviews provided.
- NEVER claim a competitor uses a specific tool, system, or technology unless it is explicitly mentioned in their reviews.
- If you don't have data for a claim, don't make the claim. Base every comparison ONLY on evidence from the actual reviews.
- Do NOT reference reviews you haven't seen — only reference the reviews provided to you.

Rules:
1. Name each competitor and their rating
2. If competitor reviews are provided, cite what THEIR customers say (actual themes and quotes)
3. Identify specific gaps: things competitors are praised for that the client is not mentioned for
4. Identify specific advantages: things the client excels at that competitors don't
5. Be blunt about market position - don't sugar-coat if the client is lagging""",
    ),
    (
        "human",
        """Compare {business_name} (rating: {client_rating}) against competitors.

Client's key themes: {client_themes}
Client review summary: {client_summary}

Competitors with data:
{competitors_text}

For each named competitor:
1. Their rating and what their customers say (if reviews provided)
2. Where {business_name} beats them and where they beat {business_name}
3. Specific opportunity the client could exploit

Then: overall market position, top 3 competitive advantages, top 3 gaps to close.""",
    ),
])


INSIGHTS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a senior business consultant. Generate insights backed by SPECIFIC DATA from the analysis. This could be any type of business — adapt to whatever industry the data describes.

CRITICAL: Every insight must cite specific numbers, quotes, or competitor names FROM THE DATA PROVIDED.
- BAD: "Customer service could be improved"
- GOOD: "3 of your 5 negative reviews specifically mention long wait times at the reception desk."

ANTI-HALLUCINATION RULES:
- NEVER invent or fabricate statistics, percentages, or specific numbers that are not directly stated in the data provided.
- NEVER claim a competitor uses a specific tool, system, or technology unless it is explicitly mentioned in their reviews.
- If you don't have data for a claim, don't make the claim. Base every insight ONLY on evidence from the actual reviews and analysis above.
- Do NOT reference reviews you haven't seen (e.g. "25% of 1-star reviews") — only reference the data provided to you.

Categories: opportunity, risk, trend, competitive, operational.
Each insight needs: a specific title, evidence-backed description, impact level, and the supporting data points.""",
    ),
    (
        "human",
        """Generate data-backed insights for {business_name}:

Sentiment: {sentiment_summary}
Themes: {theme_summary}
Competitive Position: {competitor_summary}

Generate 5-7 insights. Every insight MUST include:
1. Specific title (not generic)
2. Description citing exact data (review counts, specific topics, named competitors)
3. Impact level (high/medium/low)
4. 2-3 supporting data points from the analysis above
5. A 2-3 sentence executive summary of the most important finding""",
    ),
])


RECOMMENDATIONS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a business consultant giving SPECIFIC, data-backed recommendations. This could be any type of business — adapt to whatever industry the data describes.

CRITICAL: Recommendations must reference actual data from the analysis.
- BAD: "Enhance customer service training"
- GOOD: "Your 2 lowest-rated reviews both mention long wait times on weekends. Consider implementing an appointment or queue management system for peak hours."

ANTI-HALLUCINATION RULES:
- NEVER invent or fabricate statistics, percentages, or specific numbers that are not directly stated in the reviews provided.
- NEVER claim a competitor uses a specific tool or system unless it is explicitly mentioned in their reviews.
- If you don't have data for a claim, don't make the claim. Base every recommendation ONLY on evidence from the actual reviews.
- Do NOT reference reviews you haven't seen (e.g. "25% of 1-star reviews") — only reference the reviews provided to you.

Rules:
1. Each recommendation must cite the specific review data that motivates it
2. Implementation steps must be concrete actions, not vague suggestions
3. Expected outcomes should be measurable where possible
4. Quick wins = things you can do THIS WEEK. Not "improve training over time."

Categories: service, offerings, marketing, operations, staff, environment, value.""",
    ),
    (
        "human",
        """Create specific recommendations for {business_name}:

Insights: {insights_text}
Strengths to leverage: {strengths}
Weaknesses to fix: {weaknesses}

Generate 5-8 recommendations. For each:
1. Specific title referencing the actual issue
2. What the data says (cite review counts, quotes, competitor names)
3. Exactly what to do (concrete steps, not platitudes)
4. What success looks like (measurable outcome)
5. Priority: high/medium/low

Separate into: quick wins (this week), medium-term (1-3 months), strategic (3+ months).""",
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
        # Format reviews for the prompt - include date if available
        review_lines = []
        for i, r in enumerate(reviews):
            date_str = r.get("time", "")
            date_part = f", Date: {date_str}" if date_str else ""
            review_lines.append(
                f"Review {i+1} (Rating: {r.get('rating', 'N/A')}/5{date_part}):\n\"{r.get('text', 'No text')}\""
            )
        reviews_text = "\n\n".join(review_lines)

        llm = _get_llm()
        structured_llm = llm.with_structured_output(SentimentAnalysisResult)

        prompt = SENTIMENT_ANALYSIS_PROMPT.format(
            business_name=business_name,
            reviews_text=reviews_text,
            review_count=len(reviews),
        )

        result: SentimentAnalysisResult = await structured_llm.ainvoke(prompt)

        # Normalize scores: LLM may return on 1-5 scale or outside -1 to 1
        def _normalize_score(val: float) -> float:
            if val > 1.0:
                return min((val / 5.0) * 2 - 1, 1.0)
            if val < -1.0:
                return max(val, -1.0)
            return val

        for review in result.reviews:
            review.score = _normalize_score(review.score)
            review.confidence = max(0.0, min(review.confidence, 1.0))

        result.overall_score = _normalize_score(result.overall_score)

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
        # Format reviews for the prompt - include date for emerging theme detection
        review_lines = []
        for i, r in enumerate(reviews):
            date_str = r.get("time", "")
            date_part = f", Date: {date_str}" if date_str else ""
            review_lines.append(
                f"Review {i+1} (Rating: {r.get('rating', 'N/A')}/5{date_part}):\n\"{r.get('text', 'No text')}\""
            )
        reviews_text = "\n\n".join(review_lines)

        llm = _get_llm()
        structured_llm = llm.with_structured_output(ThemeAnalysisResult)

        prompt = THEME_EXTRACTION_PROMPT.format(
            business_name=business_name,
            reviews_text=reviews_text,
            review_count=len(reviews),
        )

        result: ThemeAnalysisResult = await structured_llm.ainvoke(prompt)

        # Fallback: if 0 themes returned but we have reviews, retry with simpler prompt
        if len(result.themes) == 0 and len(reviews) > 0:
            logger.warning(
                "analysis_themes_empty_retry",
                review_count=len(reviews),
                msg="Structured output returned 0 themes, retrying with simpler prompt",
            )
            fallback_prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "You are a business review analyst. Extract themes from customer reviews. "
                    "A theme is any topic, product, service aspect, or experience mentioned. "
                    "Even a single mention counts as a theme.",
                ),
                (
                    "human",
                    "Here are {review_count} reviews for {business_name}:\n\n{reviews_text}\n\n"
                    "List every distinct topic, product, service, or aspect mentioned. "
                    "For each: name it specifically, count how many reviews mention it, "
                    "note if sentiment is positive or negative, and quote one example (English only).",
                ),
            ]).format(
                business_name=business_name,
                reviews_text=reviews_text,
                review_count=len(reviews),
            )
            result = await structured_llm.ainvoke(fallback_prompt)
            logger.info(
                "analysis_themes_fallback_complete",
                theme_count=len(result.themes),
            )

        # Normalize average_sentiment: LLM may return on 1-5 scale instead of -1 to 1
        for theme in result.themes:
            if theme.average_sentiment > 1.0:
                theme.average_sentiment = (theme.average_sentiment / 5.0) * 2 - 1  # map 1-5 → -0.6 to 1.0
            elif theme.average_sentiment < -1.0:
                theme.average_sentiment = max(theme.average_sentiment, -1.0)

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

        # Format competitors with review data if available
        comp_texts = []
        for c in competitors[:10]:
            comp_str = (
                f"Competitor: {c.get('name', 'Unknown')}\n"
                f"- Rating: {c.get('rating', 'N/A')}\n"
                f"- Address: {c.get('address', 'N/A')}\n"
                f"- Type: {c.get('primary_type', 'N/A')}"
            )
            # Include competitor reviews if available (from Outscraper)
            comp_reviews = c.get("reviews", [])
            if comp_reviews:
                comp_str += f"\n- Reviews analyzed: {len(comp_reviews)}"
                sample_reviews = comp_reviews[:5]  # Top 5 for context
                for i, r in enumerate(sample_reviews, 1):
                    text = (r.get("text") or "")[:200]
                    rating = r.get("rating", "N/A")
                    comp_str += f'\n  Review {i} ({rating}/5): "{text}"'
            comp_texts.append(comp_str)
        competitors_text = "\n\n".join(comp_texts)

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

        try:
            result: InsightsResult = await structured_llm.ainvoke(prompt)
        except Exception as structured_err:
            # Fallback: LLM may return JSON string instead of parsed object
            logger.warning(
                "analysis_insights_structured_failed",
                error=str(structured_err),
                msg="Falling back to raw LLM + JSON parsing",
            )
            import json as _json

            raw_llm = _get_llm()
            raw_response = await raw_llm.ainvoke(prompt)
            raw_text = raw_response.content if hasattr(raw_response, "content") else str(raw_response)

            # Try to extract JSON from the response
            try:
                # Strip markdown code fences if present
                cleaned = raw_text.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                parsed = _json.loads(cleaned)
                result = InsightsResult(**parsed)
            except Exception as json_err:
                logger.error("analysis_insights_json_fallback_failed", error=str(json_err))
                # Return a minimal valid result instead of failing entirely
                result = InsightsResult(
                    insights=[],
                    executive_summary=f"Insight generation encountered a parsing issue. Raw summary: {raw_text[:300]}",
                )

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
