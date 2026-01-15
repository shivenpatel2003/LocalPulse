"""
Dynamic Configuration Adapter.

This module provides adapters that allow existing collectors, analyzers,
and report generators to work with the dynamic IndustryConfig system.

It bridges the gap between the static configuration used by the original
pipeline and the flexible, AI-generated configurations.
"""

from typing import Any, Optional

from src.config.industry_schema import (
    CompetitorConfig,
    DataFieldConfig,
    DataSourceConfig,
    DataSourceType,
    DataType,
    IndustryConfig,
    ReportConfig,
    SectionType,
    ThemeConfig,
)


# =============================================================================
# Collection Adapters
# =============================================================================

class CollectorAdapter:
    """
    Adapts dynamic config to collector interfaces.

    Provides the configuration needed by data collectors based on
    the dynamic IndustryConfig.
    """

    def __init__(self, config: IndustryConfig):
        self.config = config

    def should_collect_google_places(self) -> bool:
        """Check if Google Places collection is enabled."""
        return any(
            s.source_type == DataSourceType.GOOGLE_PLACES and s.enabled
            for s in self.config.data_sources
        )

    def should_collect_instagram(self) -> bool:
        """Check if Instagram collection is enabled."""
        return any(
            s.source_type == DataSourceType.INSTAGRAM and s.enabled
            for s in self.config.data_sources
        )

    def should_collect_tiktok(self) -> bool:
        """Check if TikTok collection is enabled."""
        return any(
            s.source_type == DataSourceType.TIKTOK and s.enabled
            for s in self.config.data_sources
        )

    def should_collect_yelp(self) -> bool:
        """Check if Yelp collection is enabled."""
        return any(
            s.source_type == DataSourceType.YELP and s.enabled
            for s in self.config.data_sources
        )

    def should_collect_tripadvisor(self) -> bool:
        """Check if TripAdvisor collection is enabled."""
        return any(
            s.source_type == DataSourceType.TRIPADVISOR and s.enabled
            for s in self.config.data_sources
        )

    def get_google_places_config(self) -> Optional[dict[str, Any]]:
        """Get Google Places search configuration."""
        for source in self.config.data_sources:
            if source.source_type == DataSourceType.GOOGLE_PLACES and source.enabled:
                return source.search_config
        return None

    def get_social_config(self, platform: str) -> Optional[dict[str, Any]]:
        """Get social media configuration for a platform."""
        platform_map = {
            "instagram": DataSourceType.INSTAGRAM,
            "tiktok": DataSourceType.TIKTOK,
            "twitter": DataSourceType.TWITTER,
            "facebook": DataSourceType.FACEBOOK,
        }
        source_type = platform_map.get(platform.lower())
        if not source_type:
            return None

        for source in self.config.data_sources:
            if source.source_type == source_type and source.enabled:
                return source.search_config
        return None

    def get_competitor_search_config(self) -> Optional[dict[str, Any]]:
        """Get competitor discovery configuration."""
        if self.config.competitor_config:
            return {
                "method": self.config.competitor_config.discovery_method.value,
                "config": self.config.competitor_config.search_config,
                "max_competitors": self.config.competitor_config.max_competitors,
                "track_reviews": self.config.competitor_config.track_their_reviews,
                "track_social": self.config.competitor_config.track_their_social,
            }
        return None

    def get_enabled_sources(self) -> list[DataSourceConfig]:
        """Get all enabled data sources."""
        return [s for s in self.config.data_sources if s.enabled]


# =============================================================================
# Analysis Adapters
# =============================================================================

class AnalyzerAdapter:
    """
    Adapts dynamic config to analyzer interfaces.

    Provides the configuration needed by sentiment analysis and
    insight generation based on the dynamic IndustryConfig.
    """

    def __init__(self, config: IndustryConfig):
        self.config = config

    def get_sentiment_prompt(self) -> str:
        """Get the sentiment analysis prompt."""
        # Check for custom prompt in sentiment config
        if self.config.sentiment_config.custom_prompt:
            return self.config.sentiment_config.custom_prompt

        # Check for prompt in prompts dict
        if "sentiment_analysis" in self.config.prompts:
            return self.config.prompts["sentiment_analysis"]

        # Generate default prompt
        themes_list = ", ".join(t.display_name for t in self.config.themes[:5])
        return f"""Analyze the following content for a {self.config.entity_name}.

Identify the sentiment (positive, negative, neutral) and extract themes.
Focus on these key themes: {themes_list}.

For each theme mentioned, provide:
1. The theme name
2. Sentiment (positive/negative/neutral)
3. Key phrases that indicate this sentiment
4. Confidence score (0.0-1.0)

Also provide an overall sentiment score from -1.0 (very negative) to 1.0 (very positive)."""

    def get_insight_prompt(self) -> str:
        """Get the insight generation prompt."""
        if "insight_generation" in self.config.prompts:
            return self.config.prompts["insight_generation"]

        kpis = [f.display_name for f in self.config.custom_fields if f.is_kpi]
        kpis_text = ", ".join(kpis) if kpis else "key metrics"

        return f"""Based on the collected data for this {self.config.entity_name}, generate actionable insights.

Focus on:
1. Key performance indicators: {kpis_text}
2. Trends over the reporting period
3. Areas of strength to leverage
4. Areas needing improvement
5. Competitive positioning

Provide specific, actionable recommendations that the business owner can implement."""

    def get_themes(self) -> list[ThemeConfig]:
        """Get all analysis themes."""
        return self.config.themes

    def get_themes_for_analysis(self) -> list[dict[str, Any]]:
        """Get themes formatted for analysis prompts."""
        return [
            {
                "name": t.name,
                "display_name": t.display_name,
                "category": t.category,
                "positive_indicators": t.positive_indicators,
                "negative_indicators": t.negative_indicators,
                "weight": t.weight,
            }
            for t in self.config.themes
        ]

    def get_theme_weights(self) -> dict[str, float]:
        """Get a mapping of theme names to weights."""
        return {t.name: t.weight for t in self.config.themes}

    def get_competitor_analysis_prompt(self) -> str:
        """Get the competitor analysis prompt."""
        if "competitor_analysis" in self.config.prompts:
            return self.config.prompts["competitor_analysis"]

        metrics = []
        if self.config.competitor_config:
            metrics = self.config.competitor_config.comparison_metrics

        metrics_text = ", ".join(metrics) if metrics else "rating and reviews"

        return f"""Compare this {self.config.entity_name} with its competitors.

Analyze:
1. Comparative metrics: {metrics_text}
2. Unique strengths and differentiators
3. Competitive threats and challenges
4. Market positioning
5. Opportunities for improvement

Provide actionable competitive intelligence."""


# =============================================================================
# Report Adapters
# =============================================================================

class ReportAdapter:
    """
    Adapts dynamic config to report generator interfaces.

    Provides the configuration needed by the report generator based on
    the dynamic IndustryConfig.
    """

    def __init__(self, config: IndustryConfig):
        self.config = config

    def get_report_name(self) -> str:
        """Get the report name."""
        return self.config.report_config.report_name

    def get_report_tone(self) -> str:
        """Get the report tone."""
        return self.config.report_config.tone.value

    def get_sections(self) -> list[dict[str, Any]]:
        """Get report sections formatted for the generator."""
        return [
            {
                "id": s.section_id,
                "title": s.title,
                "type": s.section_type.value,
                "visualization": s.visualization.value,
                "data_fields": s.data_fields,
                "ai_generated": s.ai_generated_content,
                "priority": s.priority,
            }
            for s in sorted(
                self.config.report_config.sections, key=lambda x: x.priority
            )
        ]

    def should_include_competitors(self) -> bool:
        """Check if competitor analysis should be included."""
        return self.config.report_config.include_competitor_intel

    def should_include_recommendations(self) -> bool:
        """Check if recommendations should be included."""
        return self.config.report_config.include_recommendations

    def get_kpis_for_report(self) -> list[dict[str, Any]]:
        """Get KPI fields formatted for report."""
        return [
            {
                "name": f.name,
                "display_name": f.display_name,
                "format": f.display_format,
                "track_trend": f.track_trend,
            }
            for f in self.config.custom_fields
            if f.is_kpi
        ]

    def get_executive_summary_prompt(self) -> str:
        """Get the executive summary prompt."""
        if "executive_summary" in self.config.prompts:
            return self.config.prompts["executive_summary"]

        return f"""Write a concise executive summary for this {self.config.entity_name}'s weekly intelligence report.

The summary should:
1. Highlight key performance changes
2. Identify the most important insights
3. Summarize competitive positioning
4. Preview top recommendations

Keep it brief (2-3 paragraphs) and actionable. Use a {self.config.report_config.tone.value} tone."""

    def get_recommendation_prompt(self) -> str:
        """Get the recommendation generation prompt."""
        if "recommendation" in self.config.prompts:
            return self.config.prompts["recommendation"]

        return f"""Based on the analysis, provide specific recommendations for this {self.config.entity_name}.

Structure recommendations as:
1. Priority (high/medium/low)
2. Action to take
3. Expected impact
4. Implementation difficulty

Focus on actionable items that can be implemented within the next reporting period."""

    def get_branding_config(self) -> dict[str, Any]:
        """Get custom branding configuration."""
        return self.config.report_config.custom_branding


# =============================================================================
# Graph Adapters
# =============================================================================

class GraphAdapter:
    """
    Adapts dynamic config to Neo4j graph operations.

    Provides the schema needed for knowledge graph construction.
    """

    def __init__(self, config: IndustryConfig):
        self.config = config

    def get_node_labels(self) -> list[str]:
        """Get all node labels."""
        return [n.label for n in self.config.graph_schema.nodes]

    def get_relationship_types(self) -> list[str]:
        """Get all relationship types."""
        return [r.relationship_type for r in self.config.graph_schema.relationships]

    def get_indexes(self) -> list[str]:
        """Get index definitions."""
        return self.config.graph_schema.indexes

    def get_cypher_schema(self) -> str:
        """Generate Cypher statements to create the schema."""
        statements = []

        # Create constraints
        for constraint in self.config.graph_schema.constraints:
            statements.append(constraint)

        # Create indexes
        for index in self.config.graph_schema.indexes:
            if "." in index:
                label, prop = index.split(".")
                statements.append(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
                )

        return ";\n".join(statements)


# =============================================================================
# Factory Function
# =============================================================================

class ConfigAdapters:
    """Container for all adapters for a configuration."""

    def __init__(self, config: IndustryConfig):
        self.config = config
        self.collector = CollectorAdapter(config)
        self.analyzer = AnalyzerAdapter(config)
        self.reporter = ReportAdapter(config)
        self.graph = GraphAdapter(config)


def get_adapters(config: IndustryConfig) -> ConfigAdapters:
    """Get all adapters for a configuration."""
    return ConfigAdapters(config)


async def get_adapters_for_client(client_id: str) -> ConfigAdapters:
    """Load config and get adapters for a client."""
    from src.config.config_loader import load_config

    config = await load_config(client_id)
    return ConfigAdapters(config)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "CollectorAdapter",
    "AnalyzerAdapter",
    "ReportAdapter",
    "GraphAdapter",
    "ConfigAdapters",
    "get_adapters",
    "get_adapters_for_client",
]
