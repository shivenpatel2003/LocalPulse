"""
Dynamic Industry Configuration Schema.

This module defines comprehensive Pydantic models for configuring LocalPulse
to monitor ANY type of business. The schema supports:
- Custom data fields from any source
- Multiple data source integrations
- Industry-specific themes for analysis
- Dynamic competitor tracking
- Modular report generation
- Flexible knowledge graph schemas

Generated configurations are fully production-ready and self-describing.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Enums for Type Safety
# =============================================================================

class DataType(str, Enum):
    """Supported data types for custom fields."""
    NUMBER = "number"
    TEXT = "text"
    RATING = "rating"
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    DATE = "date"
    BOOLEAN = "boolean"
    LIST = "list"
    JSON = "json"


class SourceType(str, Enum):
    """Types of data sources."""
    API = "api"
    CALCULATED = "calculated"
    MANUAL_INPUT = "manual_input"
    WEBHOOK = "webhook"
    CSV_IMPORT = "csv_import"
    GOOGLE_SHEETS = "google_sheets"
    SCRAPED = "scraped"


class DataSourceType(str, Enum):
    """Supported external data sources."""
    GOOGLE_PLACES = "google_places"
    GOOGLE_BUSINESS = "google_business"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    YOUTUBE = "youtube"
    YELP = "yelp"
    TRIPADVISOR = "tripadvisor"
    TRUSTPILOT = "trustpilot"
    CUSTOM_API = "custom_api"
    WEBHOOK = "webhook"
    MANUAL = "manual"
    CSV = "csv"
    GOOGLE_SHEETS = "google_sheets"


class AggregationType(str, Enum):
    """How to aggregate field values over time."""
    SUM = "sum"
    AVERAGE = "average"
    LATEST = "latest"
    TREND = "trend"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"
    DISTINCT_COUNT = "distinct_count"


class SyncFrequency(str, Enum):
    """How often to sync data from sources."""
    REALTIME = "realtime"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"


class MarketScope(str, Enum):
    """Geographic scope of the market."""
    LOCAL = "local"
    REGIONAL = "regional"
    NATIONAL = "national"
    GLOBAL = "global"


class ReportTone(str, Enum):
    """Tone for generated report content."""
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    TECHNICAL = "technical"
    EXECUTIVE = "executive"
    FRIENDLY = "friendly"


class ReportLength(str, Enum):
    """Length/detail level for reports."""
    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


class SectionType(str, Enum):
    """Types of report sections."""
    EXECUTIVE_SUMMARY = "executive_summary"
    KPI_CARDS = "kpi_cards"
    TREND_CHART = "trend_chart"
    THEME_BREAKDOWN = "theme_breakdown"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    COMPETITOR_TABLE = "competitor_table"
    RECOMMENDATIONS = "recommendations"
    CUSTOM_METRICS = "custom_metrics"
    ALERTS = "alerts"
    RAW_REVIEWS = "raw_reviews"
    SOCIAL_HIGHLIGHTS = "social_highlights"
    ACTION_ITEMS = "action_items"
    FORECAST = "forecast"


class VisualizationType(str, Enum):
    """Types of data visualizations."""
    CARDS = "cards"
    BAR_CHART = "bar_chart"
    LINE_CHART = "line_chart"
    PIE_CHART = "pie_chart"
    TABLE = "table"
    HEATMAP = "heatmap"
    GAUGE = "gauge"
    COMPARISON = "comparison"
    WORDCLOUD = "wordcloud"
    TIMELINE = "timeline"
    SCATTER = "scatter"
    FUNNEL = "funnel"
    MAP = "map"


class CompetitorDiscoveryMethod(str, Enum):
    """Methods for discovering competitors."""
    LOCATION_RADIUS = "location_radius"
    SEARCH_TERMS = "search_terms"
    MANUAL_LIST = "manual_list"
    SIMILAR_AUDIENCE = "similar_audience"
    SAME_CATEGORY = "same_category"
    HASHTAG_OVERLAP = "hashtag_overlap"


# =============================================================================
# Core Configuration Models
# =============================================================================

class AlertThreshold(BaseModel):
    """Configuration for field-level alerts."""
    condition: Literal["above", "below", "equals", "changes_by", "drops_below", "exceeds"]
    value: float
    message: str
    severity: Literal["info", "warning", "critical"] = "warning"
    notify_immediately: bool = False


class DataFieldConfig(BaseModel):
    """
    Custom data field configuration.

    Fields can come from APIs, manual input, webhooks, or be calculated
    from other fields. This provides complete flexibility in what metrics
    a business can track.
    """
    field_id: str = Field(default_factory=lambda: f"field_{uuid4().hex[:8]}")
    name: str = Field(..., description="Internal name, e.g., 'rebooking_rate'")
    display_name: str = Field(..., description="Human-readable name, e.g., 'Rebooking Rate'")
    description: str = Field(..., description="What this field measures")
    data_type: DataType = Field(..., description="Data type for validation and formatting")
    source_type: SourceType = Field(..., description="Where the data comes from")
    source_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific configuration (API endpoint, calculation formula, etc.)"
    )
    aggregation: AggregationType = Field(
        default=AggregationType.LATEST,
        description="How to aggregate values over time"
    )
    display_format: str = Field(
        default="{value}",
        description="Format string for display, e.g., '{value}%', '£{value}'"
    )
    unit: Optional[str] = Field(None, description="Unit of measurement")
    is_kpi: bool = Field(False, description="Show prominently in reports as KPI")
    track_trend: bool = Field(True, description="Calculate period-over-period change")
    alert_thresholds: list[AlertThreshold] = Field(
        default_factory=list,
        description="Conditions that trigger alerts"
    )
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    visible_in_reports: bool = Field(True, description="Include in generated reports")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is a valid identifier."""
        if not v.replace("_", "").isalnum():
            raise ValueError("Field name must be alphanumeric with underscores only")
        return v.lower()


class AuthConfig(BaseModel):
    """Authentication configuration for data sources."""
    auth_type: Literal["api_key", "oauth2", "basic", "bearer", "custom", "none"] = "none"
    credentials_key: Optional[str] = Field(
        None, description="Environment variable name for credentials"
    )
    oauth_config: Optional[dict[str, Any]] = None
    headers: dict[str, str] = Field(default_factory=dict)
    refresh_token_endpoint: Optional[str] = None


class RateLimitConfig(BaseModel):
    """Rate limiting configuration for API sources."""
    requests_per_minute: int = 60
    requests_per_day: int = 10000
    retry_after_seconds: int = 60
    backoff_multiplier: float = 2.0


class DataSourceConfig(BaseModel):
    """
    Flexible data source configuration.

    Supports multiple types of data sources including social media platforms,
    review sites, custom APIs, webhooks, and manual data entry.
    """
    source_id: str = Field(default_factory=lambda: f"src_{uuid4().hex[:8]}")
    source_type: DataSourceType = Field(..., description="Type of data source")
    display_name: str = Field(..., description="Human-readable name")
    description: Optional[str] = None
    enabled: bool = Field(True, description="Whether this source is active")

    # Authentication
    auth_required: bool = Field(False, description="Whether authentication is needed")
    auth_config: Optional[AuthConfig] = None

    # Search/Query Configuration
    search_config: dict[str, Any] = Field(
        default_factory=dict,
        description="How to find data (search terms, place_id, username, etc.)"
    )

    # Field Mapping
    fields_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map source fields to our custom fields"
    )

    # Sync Settings
    sync_frequency: SyncFrequency = Field(
        default=SyncFrequency.DAILY,
        description="How often to sync data"
    )
    last_sync: Optional[datetime] = None

    # Rate Limiting
    rate_limits: Optional[RateLimitConfig] = None

    # Data Processing
    transform_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Data transformation rules"
    )
    filter_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Data filtering rules"
    )

    # Priority for multi-source fields
    priority: int = Field(1, description="Priority when multiple sources provide same field")


class ThemeConfig(BaseModel):
    """
    Theme configuration for sentiment and content analysis.

    Themes define patterns that the AI should look for when analyzing
    reviews, social posts, and other content. Each industry will have
    different themes that matter.
    """
    theme_id: str = Field(default_factory=lambda: f"theme_{uuid4().hex[:8]}")
    name: str = Field(..., description="Internal name, e.g., 'service_quality'")
    display_name: str = Field(..., description="Human-readable name, e.g., 'Service Quality'")
    description: str = Field(..., description="What this theme captures")
    category: str = Field(..., description="Theme category, e.g., 'Service', 'Product', 'Value'")

    # Indicators for sentiment classification
    positive_indicators: list[str] = Field(
        ..., description="Words/phrases indicating positive sentiment"
    )
    negative_indicators: list[str] = Field(
        ..., description="Words/phrases indicating negative sentiment"
    )
    neutral_indicators: list[str] = Field(
        default_factory=list,
        description="Words/phrases indicating neutral sentiment"
    )

    # Analysis Configuration
    weight: float = Field(
        1.0, ge=0.0, le=1.0,
        description="Importance in overall scoring (0.0 - 1.0)"
    )
    industry_specific: bool = Field(
        False, description="Is this unique to this industry?"
    )

    # Suggested Actions
    suggested_actions: dict[str, list[str]] = Field(
        default_factory=lambda: {"positive": [], "negative": [], "neutral": []},
        description="What to recommend based on sentiment"
    )

    # Analysis Prompts
    analysis_prompt: Optional[str] = Field(
        None, description="Custom prompt for analyzing this theme"
    )

    # Trending
    track_over_time: bool = Field(True, description="Track theme mentions over time")


class CompetitorConfig(BaseModel):
    """
    Competitor identification and tracking configuration.

    Defines how to discover competitors and what to track about them.
    """
    discovery_method: CompetitorDiscoveryMethod = Field(
        ..., description="How to find competitors"
    )
    search_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Method-specific search configuration"
    )

    # What to compare
    comparison_metrics: list[str] = Field(
        default_factory=list,
        description="Which metrics to compare with competitors"
    )

    # Tracking options
    track_their_reviews: bool = Field(True, description="Collect competitor reviews")
    track_their_social: bool = Field(False, description="Collect competitor social media")
    track_their_pricing: bool = Field(False, description="Track competitor pricing")
    track_their_offerings: bool = Field(False, description="Track competitor services/products")

    # Limits
    max_competitors: int = Field(10, description="Maximum number of competitors to track")
    update_frequency: SyncFrequency = Field(
        SyncFrequency.WEEKLY,
        description="How often to update competitor data"
    )

    # Analysis
    generate_competitive_insights: bool = Field(
        True, description="Generate AI insights about competitive position"
    )

    # Manual competitors (always tracked regardless of discovery)
    manual_competitors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Manually specified competitors"
    )


class ReportSection(BaseModel):
    """
    Modular report section configuration.

    Reports are composed of configurable sections that can be
    arranged and customized for each business.
    """
    section_id: str = Field(default_factory=lambda: f"sec_{uuid4().hex[:8]}")
    title: str = Field(..., description="Section title")
    description: Optional[str] = Field(None, description="Section description")
    section_type: SectionType = Field(..., description="Type of section")

    # Data Configuration
    data_fields: list[str] = Field(
        default_factory=list,
        description="Which fields to display in this section"
    )
    data_filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Filters to apply to data"
    )

    # Visualization
    visualization: VisualizationType = Field(
        VisualizationType.TABLE,
        description="How to visualize the data"
    )
    visualization_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Visualization-specific settings"
    )

    # AI Generation
    ai_generated_content: bool = Field(
        True, description="Should Claude write analysis for this section?"
    )
    ai_prompt_override: Optional[str] = Field(
        None, description="Custom prompt for AI-generated content"
    )

    # Layout
    priority: int = Field(1, description="Order in report (lower = earlier)")
    full_width: bool = Field(False, description="Span full width of report")
    collapsible: bool = Field(False, description="Allow section to be collapsed")

    # Conditional Display
    show_if_empty: bool = Field(False, description="Show section even if no data")
    condition: Optional[str] = Field(
        None, description="Condition for showing section (e.g., 'reviews_count > 0')"
    )


class DeliveryConfig(BaseModel):
    """Report delivery configuration."""
    email: Optional[dict[str, Any]] = Field(
        None, description="Email delivery settings"
    )
    slack: Optional[dict[str, Any]] = Field(
        None, description="Slack delivery settings"
    )
    webhook: Optional[dict[str, Any]] = Field(
        None, description="Webhook delivery settings"
    )
    dashboard: Optional[dict[str, Any]] = Field(
        None, description="Dashboard display settings"
    )
    pdf_export: bool = Field(True, description="Generate PDF version")
    csv_export: bool = Field(False, description="Generate CSV data export")


class ReportConfig(BaseModel):
    """
    Complete report configuration.

    Defines the structure, content, and delivery of generated reports.
    """
    report_name: str = Field(..., description="Name of the report")
    report_description: Optional[str] = None

    # Sections
    sections: list[ReportSection] = Field(
        default_factory=list,
        description="Report sections in order"
    )

    # Style
    tone: ReportTone = Field(
        ReportTone.PROFESSIONAL,
        description="Tone for AI-generated content"
    )
    length: ReportLength = Field(
        ReportLength.STANDARD,
        description="Overall report length"
    )

    # Content Options
    include_raw_data: bool = Field(False, description="Include raw data tables")
    include_recommendations: bool = Field(True, description="Include AI recommendations")
    include_competitor_intel: bool = Field(True, description="Include competitor analysis")
    include_trend_analysis: bool = Field(True, description="Include trend analysis")
    include_alerts: bool = Field(True, description="Include triggered alerts")

    # Time Period
    default_period: Literal["day", "week", "month", "quarter", "year"] = "week"
    comparison_period: Literal["previous", "same_last_year", "none"] = "previous"

    # Branding
    custom_branding: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom colors, logo, etc."
    )

    # Delivery
    delivery: DeliveryConfig = Field(
        default_factory=DeliveryConfig,
        description="Report delivery settings"
    )

    # Schedule
    generation_schedule: Optional[str] = Field(
        None, description="Cron expression for scheduled generation"
    )


class NodeSchema(BaseModel):
    """Knowledge graph node definition."""
    label: str = Field(..., description="Node label, e.g., 'Business'")
    properties: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Node properties"
    )
    required_properties: list[str] = Field(
        default_factory=list,
        description="Required property names"
    )


class RelationshipSchema(BaseModel):
    """Knowledge graph relationship definition."""
    from_node: str = Field(..., description="Source node label")
    to_node: str = Field(..., description="Target node label")
    relationship_type: str = Field(..., description="Relationship type, e.g., 'HAS_REVIEW'")
    properties: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Relationship properties"
    )


class GraphSchemaConfig(BaseModel):
    """
    Dynamic knowledge graph schema configuration.

    Defines the structure of the Neo4j knowledge graph for this
    business type.
    """
    nodes: list[NodeSchema] = Field(
        default_factory=list,
        description="Node definitions"
    )
    relationships: list[RelationshipSchema] = Field(
        default_factory=list,
        description="Relationship definitions"
    )
    indexes: list[str] = Field(
        default_factory=list,
        description="Properties to index for performance"
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Uniqueness constraints"
    )


class AlertRule(BaseModel):
    """Alert rule configuration."""
    rule_id: str = Field(default_factory=lambda: f"alert_{uuid4().hex[:8]}")
    name: str
    description: Optional[str] = None
    condition: str = Field(..., description="Condition expression")
    severity: Literal["info", "warning", "critical"] = "warning"
    notification_channels: list[str] = Field(default_factory=list)
    cooldown_minutes: int = Field(60, description="Minimum time between alerts")
    enabled: bool = True


class SentimentConfig(BaseModel):
    """Overall sentiment analysis configuration."""
    model: str = Field("claude-sonnet-4-20250514", description="Model for sentiment analysis")
    include_reasoning: bool = Field(True, description="Include reasoning in output")
    confidence_threshold: float = Field(0.7, description="Minimum confidence for classification")
    multi_label: bool = Field(True, description="Allow multiple themes per item")
    aggregate_method: Literal["weighted_average", "majority_vote", "all"] = "weighted_average"
    custom_prompt: Optional[str] = None


# =============================================================================
# Master Configuration Model
# =============================================================================

class IndustryConfig(BaseModel):
    """
    Master configuration for monitoring any business.

    This is the complete, self-describing configuration that defines
    everything needed to monitor a specific business type. It includes:
    - Business identity and context
    - Data sources and custom fields
    - Analysis themes and sentiment settings
    - Competitor tracking
    - Report generation
    - Knowledge graph schema
    - AI prompts tailored to this business
    - Alert rules

    Configurations can be AI-generated from natural language descriptions
    or manually created.
    """
    # Identity
    config_id: str = Field(default_factory=lambda: str(uuid4()))
    config_version: str = Field("1.0", description="Schema version for migrations")
    config_name: str = Field(..., description="Name for this configuration")

    # Business Profile
    industry_name: str = Field(..., description="Industry name, e.g., 'Pet Services'")
    industry_category: str = Field(..., description="Category, e.g., 'Local Services'")
    business_type: str = Field(..., description="Specific type, e.g., 'Dog Grooming Salon'")
    entity_name: str = Field(..., description="Singular entity name for natural language, e.g., 'salon'")
    entity_name_plural: str = Field(..., description="Plural entity name, e.g., 'salons'")
    business_description: Optional[str] = Field(None, description="Detailed description")

    # Location & Market
    location: Optional[str] = Field(None, description="Primary location")
    market_scope: MarketScope = Field(
        MarketScope.LOCAL,
        description="Geographic scope of the market"
    )
    target_audience: Optional[str] = Field(None, description="Description of target customers")

    # Data Architecture
    custom_fields: list[DataFieldConfig] = Field(
        default_factory=list,
        description="Custom data fields to track"
    )
    data_sources: list[DataSourceConfig] = Field(
        default_factory=list,
        description="Data sources to collect from"
    )

    # Analysis Configuration
    themes: list[ThemeConfig] = Field(
        default_factory=list,
        description="Themes for content analysis"
    )
    sentiment_config: SentimentConfig = Field(
        default_factory=SentimentConfig,
        description="Sentiment analysis settings"
    )

    # Competitive Intelligence
    competitor_config: Optional[CompetitorConfig] = Field(
        None, description="Competitor tracking configuration"
    )

    # Reporting
    report_config: ReportConfig = Field(
        ..., description="Report generation configuration"
    )

    # Knowledge Graph
    graph_schema: GraphSchemaConfig = Field(
        default_factory=GraphSchemaConfig,
        description="Knowledge graph schema"
    )

    # AI Prompts (generated specifically for this business)
    prompts: dict[str, str] = Field(
        default_factory=dict,
        description="Custom AI prompts for various tasks"
    )

    # Alerts & Notifications
    alert_rules: list[AlertRule] = Field(
        default_factory=list,
        description="Alert rules"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Literal["ai_generated", "manual", "template"] = "ai_generated"
    source_description: str = Field(
        ..., description="Original user input that generated this config"
    )
    generation_reasoning: str = Field(
        "", description="AI's explanation of configuration choices"
    )

    # Status
    is_active: bool = Field(True, description="Whether this config is active")
    is_validated: bool = Field(False, description="Whether config has been validated")
    validation_errors: list[str] = Field(default_factory=list)

    def get_kpi_fields(self) -> list[DataFieldConfig]:
        """Get all fields marked as KPIs."""
        return [f for f in self.custom_fields if f.is_kpi]

    def get_enabled_sources(self) -> list[DataSourceConfig]:
        """Get all enabled data sources."""
        return [s for s in self.data_sources if s.enabled]

    def get_themes_by_category(self) -> dict[str, list[ThemeConfig]]:
        """Group themes by category."""
        result: dict[str, list[ThemeConfig]] = {}
        for theme in self.themes:
            if theme.category not in result:
                result[theme.category] = []
            result[theme.category].append(theme)
        return result

    def get_prompt(self, prompt_name: str, default: str = "") -> str:
        """Get a prompt by name with optional default."""
        return self.prompts.get(prompt_name, default)

    def validate_config(self) -> tuple[bool, list[str]]:
        """Validate the configuration is complete and consistent."""
        errors: list[str] = []

        # Check required fields
        if not self.custom_fields:
            errors.append("At least one custom field is required")

        if not self.data_sources:
            errors.append("At least one data source is required")

        if not self.themes:
            errors.append("At least one analysis theme is required")

        if not self.report_config.sections:
            errors.append("Report must have at least one section")

        # Check field references in report sections
        field_names = {f.name for f in self.custom_fields}
        for section in self.report_config.sections:
            for field_ref in section.data_fields:
                if field_ref not in field_names and field_ref not in ["*", "all"]:
                    errors.append(f"Report section '{section.title}' references unknown field: {field_ref}")

        # Check competitor config if tracking is enabled
        if self.competitor_config:
            if not self.competitor_config.comparison_metrics:
                errors.append("Competitor config must specify comparison metrics")

        self.validation_errors = errors
        self.is_validated = len(errors) == 0
        return self.is_validated, errors


# =============================================================================
# Template Configurations
# =============================================================================

def create_restaurant_template() -> IndustryConfig:
    """Create a template configuration for restaurants."""
    return IndustryConfig(
        config_name="Restaurant Template",
        industry_name="Food & Beverage",
        industry_category="Hospitality",
        business_type="Restaurant",
        entity_name="restaurant",
        entity_name_plural="restaurants",
        market_scope=MarketScope.LOCAL,
        custom_fields=[
            DataFieldConfig(
                name="google_rating",
                display_name="Google Rating",
                description="Average rating on Google",
                data_type=DataType.RATING,
                source_type=SourceType.API,
                source_config={"source": "google_places", "field": "rating"},
                aggregation=AggregationType.LATEST,
                display_format="{value} ★",
                is_kpi=True,
            ),
            DataFieldConfig(
                name="review_count",
                display_name="Total Reviews",
                description="Number of Google reviews",
                data_type=DataType.NUMBER,
                source_type=SourceType.API,
                source_config={"source": "google_places", "field": "user_ratings_total"},
                aggregation=AggregationType.LATEST,
                display_format="{value}",
                is_kpi=True,
            ),
            DataFieldConfig(
                name="sentiment_score",
                display_name="Sentiment Score",
                description="Overall sentiment from reviews",
                data_type=DataType.PERCENTAGE,
                source_type=SourceType.CALCULATED,
                source_config={"calculation": "average_sentiment"},
                aggregation=AggregationType.AVERAGE,
                display_format="{value}%",
                is_kpi=True,
            ),
        ],
        data_sources=[
            DataSourceConfig(
                source_type=DataSourceType.GOOGLE_PLACES,
                display_name="Google Places",
                enabled=True,
                search_config={"search_type": "place_id"},
                sync_frequency=SyncFrequency.DAILY,
            ),
        ],
        themes=[
            ThemeConfig(
                name="food_quality",
                display_name="Food Quality",
                description="Quality of food and dishes",
                category="Product",
                positive_indicators=["delicious", "fresh", "tasty", "amazing food", "best meal"],
                negative_indicators=["bland", "cold food", "undercooked", "stale", "disappointing"],
                weight=1.0,
                industry_specific=True,
            ),
            ThemeConfig(
                name="service",
                display_name="Service",
                description="Staff service and hospitality",
                category="Service",
                positive_indicators=["friendly staff", "attentive", "great service", "welcoming"],
                negative_indicators=["rude", "slow service", "ignored", "unprofessional"],
                weight=0.9,
                industry_specific=False,
            ),
            ThemeConfig(
                name="ambiance",
                display_name="Ambiance",
                description="Restaurant atmosphere and decor",
                category="Experience",
                positive_indicators=["cozy", "nice atmosphere", "beautiful decor", "romantic"],
                negative_indicators=["noisy", "cramped", "dirty", "uncomfortable"],
                weight=0.7,
                industry_specific=True,
            ),
            ThemeConfig(
                name="value",
                display_name="Value for Money",
                description="Price-to-quality ratio",
                category="Value",
                positive_indicators=["good value", "worth it", "reasonable prices", "great deal"],
                negative_indicators=["overpriced", "expensive", "not worth", "rip off"],
                weight=0.8,
                industry_specific=False,
            ),
        ],
        competitor_config=CompetitorConfig(
            discovery_method=CompetitorDiscoveryMethod.LOCATION_RADIUS,
            search_config={"radius_miles": 2, "same_cuisine": True},
            comparison_metrics=["google_rating", "review_count", "sentiment_score"],
            track_their_reviews=True,
            max_competitors=10,
        ),
        report_config=ReportConfig(
            report_name="Weekly Restaurant Intelligence Report",
            tone=ReportTone.PROFESSIONAL,
            length=ReportLength.STANDARD,
            sections=[
                ReportSection(
                    title="Executive Summary",
                    section_type=SectionType.EXECUTIVE_SUMMARY,
                    visualization=VisualizationType.CARDS,
                    ai_generated_content=True,
                    priority=1,
                ),
                ReportSection(
                    title="Key Metrics",
                    section_type=SectionType.KPI_CARDS,
                    data_fields=["google_rating", "review_count", "sentiment_score"],
                    visualization=VisualizationType.CARDS,
                    priority=2,
                ),
                ReportSection(
                    title="Sentiment Trends",
                    section_type=SectionType.TREND_CHART,
                    data_fields=["sentiment_score"],
                    visualization=VisualizationType.LINE_CHART,
                    priority=3,
                ),
                ReportSection(
                    title="Theme Analysis",
                    section_type=SectionType.THEME_BREAKDOWN,
                    visualization=VisualizationType.BAR_CHART,
                    ai_generated_content=True,
                    priority=4,
                ),
                ReportSection(
                    title="Competitor Comparison",
                    section_type=SectionType.COMPETITOR_TABLE,
                    visualization=VisualizationType.TABLE,
                    priority=5,
                ),
                ReportSection(
                    title="Recommendations",
                    section_type=SectionType.RECOMMENDATIONS,
                    visualization=VisualizationType.CARDS,
                    ai_generated_content=True,
                    priority=6,
                ),
            ],
            include_recommendations=True,
            include_competitor_intel=True,
        ),
        graph_schema=GraphSchemaConfig(
            nodes=[
                NodeSchema(label="Business", properties=[
                    {"name": "place_id", "type": "string"},
                    {"name": "name", "type": "string"},
                    {"name": "cuisine", "type": "string"},
                ]),
                NodeSchema(label="Review", properties=[
                    {"name": "text", "type": "string"},
                    {"name": "rating", "type": "float"},
                    {"name": "date", "type": "datetime"},
                ]),
                NodeSchema(label="Theme", properties=[
                    {"name": "name", "type": "string"},
                    {"name": "sentiment", "type": "string"},
                ]),
            ],
            relationships=[
                RelationshipSchema(
                    from_node="Business",
                    to_node="Review",
                    relationship_type="HAS_REVIEW",
                ),
                RelationshipSchema(
                    from_node="Review",
                    to_node="Theme",
                    relationship_type="MENTIONS",
                    properties=[{"name": "sentiment_score", "type": "float"}],
                ),
                RelationshipSchema(
                    from_node="Business",
                    to_node="Business",
                    relationship_type="COMPETES_WITH",
                ),
            ],
            indexes=["Business.place_id", "Review.date"],
        ),
        prompts={
            "sentiment_analysis": "Analyze the following review for a {entity_name}. Identify themes and sentiment...",
            "insight_generation": "Based on the collected data for this {entity_name}, generate actionable insights...",
            "competitor_analysis": "Compare this {entity_name} with its competitors and identify strengths and weaknesses...",
            "recommendation": "Based on the analysis, provide specific recommendations for improving this {entity_name}...",
        },
        source_description="Restaurant template configuration",
        created_by="template",
    )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Enums
    "DataType",
    "SourceType",
    "DataSourceType",
    "AggregationType",
    "SyncFrequency",
    "MarketScope",
    "ReportTone",
    "ReportLength",
    "SectionType",
    "VisualizationType",
    "CompetitorDiscoveryMethod",
    # Models
    "AlertThreshold",
    "DataFieldConfig",
    "AuthConfig",
    "RateLimitConfig",
    "DataSourceConfig",
    "ThemeConfig",
    "CompetitorConfig",
    "ReportSection",
    "DeliveryConfig",
    "ReportConfig",
    "NodeSchema",
    "RelationshipSchema",
    "GraphSchemaConfig",
    "AlertRule",
    "SentimentConfig",
    "IndustryConfig",
    # Templates
    "create_restaurant_template",
]
