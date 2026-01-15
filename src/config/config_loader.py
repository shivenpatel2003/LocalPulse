"""
Configuration Loader.

This module provides functions to load IndustryConfig objects from various
sources (Supabase, files, or templates) and make them available to the
rest of the LocalPulse pipeline.

The config loader is the bridge between stored configurations and the
runtime components (collectors, analyzers, reporters).
"""

from datetime import datetime
from functools import lru_cache
from typing import Any, Optional
from uuid import UUID

from src.config.industry_schema import (
    AggregationType,
    AlertRule,
    AlertThreshold,
    AuthConfig,
    CompetitorConfig,
    CompetitorDiscoveryMethod,
    DataFieldConfig,
    DataSourceConfig,
    DataSourceType,
    DataType,
    DeliveryConfig,
    GraphSchemaConfig,
    IndustryConfig,
    MarketScope,
    NodeSchema,
    RateLimitConfig,
    RelationshipSchema,
    ReportConfig,
    ReportLength,
    ReportSection,
    ReportTone,
    SectionType,
    SentimentConfig,
    SourceType,
    SyncFrequency,
    ThemeConfig,
    VisualizationType,
    create_restaurant_template,
)
from src.config.settings import get_settings


# =============================================================================
# Exceptions
# =============================================================================

class ConfigNotFoundError(Exception):
    """Raised when a configuration cannot be found."""
    pass


class ConfigValidationError(Exception):
    """Raised when a configuration fails validation."""
    pass


class ConfigLoadError(Exception):
    """Raised when a configuration cannot be loaded."""
    pass


# =============================================================================
# Config Cache
# =============================================================================

class ConfigCache:
    """
    In-memory cache for loaded configurations.

    Caches configurations to avoid repeated database queries within
    a short time window.
    """

    def __init__(self, ttl_seconds: int = 300):
        """Initialize cache with TTL in seconds."""
        self._cache: dict[str, tuple[IndustryConfig, datetime]] = {}
        self._ttl = ttl_seconds

    def get(self, client_id: str) -> Optional[IndustryConfig]:
        """Get a config from cache if not expired."""
        if client_id in self._cache:
            config, timestamp = self._cache[client_id]
            if (datetime.utcnow() - timestamp).total_seconds() < self._ttl:
                return config
            else:
                # Expired, remove from cache
                del self._cache[client_id]
        return None

    def set(self, client_id: str, config: IndustryConfig) -> None:
        """Add a config to the cache."""
        self._cache[client_id] = (config, datetime.utcnow())

    def invalidate(self, client_id: str) -> None:
        """Remove a config from the cache."""
        if client_id in self._cache:
            del self._cache[client_id]

    def clear(self) -> None:
        """Clear all cached configs."""
        self._cache.clear()


# Global cache instance
_config_cache = ConfigCache()


# =============================================================================
# Config Building Functions
# =============================================================================

def _build_config_from_json(config_data: dict[str, Any]) -> IndustryConfig:
    """
    Build an IndustryConfig from a JSON dictionary.

    This is used when loading configs from Supabase where they're stored
    as JSONB.
    """
    try:
        # Build custom fields
        custom_fields = []
        for field_data in config_data.get("custom_fields", []):
            alert_thresholds = [
                AlertThreshold(**t) for t in field_data.get("alert_thresholds", [])
            ]
            custom_fields.append(DataFieldConfig(
                field_id=field_data.get("field_id", ""),
                name=field_data.get("name", ""),
                display_name=field_data.get("display_name", ""),
                description=field_data.get("description", ""),
                data_type=DataType(field_data.get("data_type", "text")),
                source_type=SourceType(field_data.get("source_type", "manual_input")),
                source_config=field_data.get("source_config", {}),
                aggregation=AggregationType(field_data.get("aggregation", "latest")),
                display_format=field_data.get("display_format", "{value}"),
                unit=field_data.get("unit"),
                is_kpi=field_data.get("is_kpi", False),
                track_trend=field_data.get("track_trend", True),
                alert_thresholds=alert_thresholds,
                tags=field_data.get("tags", []),
                visible_in_reports=field_data.get("visible_in_reports", True),
            ))

        # Build data sources
        data_sources = []
        for source_data in config_data.get("data_sources", []):
            auth_config = None
            if source_data.get("auth_config"):
                auth_config = AuthConfig(**source_data["auth_config"])

            rate_limits = None
            if source_data.get("rate_limits"):
                rate_limits = RateLimitConfig(**source_data["rate_limits"])

            data_sources.append(DataSourceConfig(
                source_id=source_data.get("source_id", ""),
                source_type=DataSourceType(source_data.get("source_type", "manual")),
                display_name=source_data.get("display_name", ""),
                description=source_data.get("description"),
                enabled=source_data.get("enabled", True),
                auth_required=source_data.get("auth_required", False),
                auth_config=auth_config,
                search_config=source_data.get("search_config", {}),
                fields_mapping=source_data.get("fields_mapping", {}),
                sync_frequency=SyncFrequency(source_data.get("sync_frequency", "daily")),
                rate_limits=rate_limits,
                transform_config=source_data.get("transform_config", {}),
                filter_config=source_data.get("filter_config", {}),
                priority=source_data.get("priority", 1),
            ))

        # Build themes
        themes = []
        for theme_data in config_data.get("themes", []):
            themes.append(ThemeConfig(
                theme_id=theme_data.get("theme_id", ""),
                name=theme_data.get("name", ""),
                display_name=theme_data.get("display_name", ""),
                description=theme_data.get("description", ""),
                category=theme_data.get("category", "General"),
                positive_indicators=theme_data.get("positive_indicators", []),
                negative_indicators=theme_data.get("negative_indicators", []),
                neutral_indicators=theme_data.get("neutral_indicators", []),
                weight=theme_data.get("weight", 1.0),
                industry_specific=theme_data.get("industry_specific", False),
                suggested_actions=theme_data.get("suggested_actions", {}),
                analysis_prompt=theme_data.get("analysis_prompt"),
                track_over_time=theme_data.get("track_over_time", True),
            ))

        # Build sentiment config
        sentiment_data = config_data.get("sentiment_config", {})
        sentiment_config = SentimentConfig(
            model=sentiment_data.get("model", "claude-sonnet-4-20250514"),
            include_reasoning=sentiment_data.get("include_reasoning", True),
            confidence_threshold=sentiment_data.get("confidence_threshold", 0.7),
            multi_label=sentiment_data.get("multi_label", True),
            aggregate_method=sentiment_data.get("aggregate_method", "weighted_average"),
            custom_prompt=sentiment_data.get("custom_prompt"),
        )

        # Build competitor config
        competitor_config = None
        if config_data.get("competitor_config"):
            cc = config_data["competitor_config"]
            competitor_config = CompetitorConfig(
                discovery_method=CompetitorDiscoveryMethod(
                    cc.get("discovery_method", "location_radius")
                ),
                search_config=cc.get("search_config", {}),
                comparison_metrics=cc.get("comparison_metrics", []),
                track_their_reviews=cc.get("track_their_reviews", True),
                track_their_social=cc.get("track_their_social", False),
                track_their_pricing=cc.get("track_their_pricing", False),
                track_their_offerings=cc.get("track_their_offerings", False),
                max_competitors=cc.get("max_competitors", 10),
                update_frequency=SyncFrequency(cc.get("update_frequency", "weekly")),
                generate_competitive_insights=cc.get("generate_competitive_insights", True),
                manual_competitors=cc.get("manual_competitors", []),
            )

        # Build report sections
        sections = []
        report_data = config_data.get("report_config", {})
        for sec_data in report_data.get("sections", []):
            sections.append(ReportSection(
                section_id=sec_data.get("section_id", ""),
                title=sec_data.get("title", ""),
                description=sec_data.get("description"),
                section_type=SectionType(sec_data.get("section_type", "custom_metrics")),
                data_fields=sec_data.get("data_fields", []),
                data_filters=sec_data.get("data_filters", {}),
                visualization=VisualizationType(sec_data.get("visualization", "table")),
                visualization_config=sec_data.get("visualization_config", {}),
                ai_generated_content=sec_data.get("ai_generated_content", True),
                ai_prompt_override=sec_data.get("ai_prompt_override"),
                priority=sec_data.get("priority", 1),
                full_width=sec_data.get("full_width", False),
                collapsible=sec_data.get("collapsible", False),
                show_if_empty=sec_data.get("show_if_empty", False),
                condition=sec_data.get("condition"),
            ))

        # Build delivery config
        delivery_data = report_data.get("delivery", {})
        delivery_config = DeliveryConfig(
            email=delivery_data.get("email"),
            slack=delivery_data.get("slack"),
            webhook=delivery_data.get("webhook"),
            dashboard=delivery_data.get("dashboard"),
            pdf_export=delivery_data.get("pdf_export", True),
            csv_export=delivery_data.get("csv_export", False),
        )

        # Build report config
        report_config = ReportConfig(
            report_name=report_data.get("report_name", "Weekly Intelligence Report"),
            report_description=report_data.get("report_description"),
            sections=sections,
            tone=ReportTone(report_data.get("tone", "professional")),
            length=ReportLength(report_data.get("length", "standard")),
            include_raw_data=report_data.get("include_raw_data", False),
            include_recommendations=report_data.get("include_recommendations", True),
            include_competitor_intel=report_data.get("include_competitor_intel", True),
            include_trend_analysis=report_data.get("include_trend_analysis", True),
            include_alerts=report_data.get("include_alerts", True),
            default_period=report_data.get("default_period", "week"),
            comparison_period=report_data.get("comparison_period", "previous"),
            custom_branding=report_data.get("custom_branding", {}),
            delivery=delivery_config,
            generation_schedule=report_data.get("generation_schedule"),
        )

        # Build graph schema
        graph_data = config_data.get("graph_schema", {})
        nodes = [
            NodeSchema(
                label=n.get("label", ""),
                properties=n.get("properties", []),
                required_properties=n.get("required_properties", []),
            )
            for n in graph_data.get("nodes", [])
        ]
        relationships = [
            RelationshipSchema(
                from_node=r.get("from_node", ""),
                to_node=r.get("to_node", ""),
                relationship_type=r.get("relationship_type", ""),
                properties=r.get("properties", []),
            )
            for r in graph_data.get("relationships", [])
        ]
        graph_schema = GraphSchemaConfig(
            nodes=nodes,
            relationships=relationships,
            indexes=graph_data.get("indexes", []),
            constraints=graph_data.get("constraints", []),
        )

        # Build alert rules
        alert_rules = []
        for rule_data in config_data.get("alert_rules", []):
            alert_rules.append(AlertRule(
                rule_id=rule_data.get("rule_id", ""),
                name=rule_data.get("name", ""),
                description=rule_data.get("description"),
                condition=rule_data.get("condition", ""),
                severity=rule_data.get("severity", "warning"),
                notification_channels=rule_data.get("notification_channels", []),
                cooldown_minutes=rule_data.get("cooldown_minutes", 60),
                enabled=rule_data.get("enabled", True),
            ))

        # Create the config
        return IndustryConfig(
            config_id=config_data.get("config_id", ""),
            config_version=config_data.get("config_version", "1.0"),
            config_name=config_data.get("config_name", ""),
            industry_name=config_data.get("industry_name", ""),
            industry_category=config_data.get("industry_category", ""),
            business_type=config_data.get("business_type", ""),
            entity_name=config_data.get("entity_name", "business"),
            entity_name_plural=config_data.get("entity_name_plural", "businesses"),
            business_description=config_data.get("business_description"),
            location=config_data.get("location"),
            market_scope=MarketScope(config_data.get("market_scope", "local")),
            target_audience=config_data.get("target_audience"),
            custom_fields=custom_fields,
            data_sources=data_sources,
            themes=themes,
            sentiment_config=sentiment_config,
            competitor_config=competitor_config,
            report_config=report_config,
            graph_schema=graph_schema,
            prompts=config_data.get("prompts", {}),
            alert_rules=alert_rules,
            created_at=datetime.fromisoformat(config_data["created_at"])
                if config_data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(config_data["updated_at"])
                if config_data.get("updated_at") else datetime.utcnow(),
            created_by=config_data.get("created_by", "ai_generated"),
            source_description=config_data.get("source_description", ""),
            generation_reasoning=config_data.get("generation_reasoning", ""),
            is_active=config_data.get("is_active", True),
            is_validated=config_data.get("is_validated", False),
            validation_errors=config_data.get("validation_errors", []),
        )

    except Exception as e:
        raise ConfigLoadError(f"Failed to build config from JSON: {str(e)}")


# =============================================================================
# Main Loader Functions
# =============================================================================

async def load_config(client_id: str) -> IndustryConfig:
    """
    Load an IndustryConfig for a client.

    This is the main function used by the pipeline to get the configuration
    for a specific client. It first checks the cache, then falls back to
    Supabase.

    Args:
        client_id: The UUID of the client.

    Returns:
        The IndustryConfig for the client.

    Raises:
        ConfigNotFoundError: If no config exists for the client.
        ConfigLoadError: If the config cannot be loaded.
    """
    # Check cache first
    cached = _config_cache.get(client_id)
    if cached:
        return cached

    # Load from Supabase
    try:
        from supabase import create_client

        settings = get_settings()
        supabase = create_client(
            settings.supabase_url,
            settings.supabase_key.get_secret_value(),
        )

        result = supabase.table("industry_configs").select("config_data").eq(
            "client_id", client_id
        ).eq("status", "active").execute()

        if not result.data:
            raise ConfigNotFoundError(f"No active config found for client: {client_id}")

        config_data = result.data[0]["config_data"]
        config = _build_config_from_json(config_data)

        # Validate the config
        is_valid, errors = config.validate_config()
        if not is_valid:
            raise ConfigValidationError(
                f"Config validation failed: {'; '.join(errors)}"
            )

        # Cache the config
        _config_cache.set(client_id, config)

        return config

    except ConfigNotFoundError:
        raise
    except ConfigValidationError:
        raise
    except Exception as e:
        raise ConfigLoadError(f"Failed to load config for client {client_id}: {str(e)}")


async def load_config_or_default(client_id: str) -> IndustryConfig:
    """
    Load a config for a client, or return a default restaurant template.

    This is useful for backwards compatibility with clients that don't
    have a custom configuration.
    """
    try:
        return await load_config(client_id)
    except ConfigNotFoundError:
        # Return the default restaurant template
        return create_restaurant_template()


def load_config_sync(client_id: str) -> IndustryConfig:
    """
    Synchronous version of load_config for non-async contexts.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(load_config(client_id))


async def save_config(client_id: str, config: IndustryConfig) -> None:
    """
    Save an IndustryConfig for a client.

    This creates or updates the configuration in Supabase.
    """
    try:
        from supabase import create_client

        settings = get_settings()
        supabase = create_client(
            settings.supabase_url,
            settings.supabase_key.get_secret_value(),
        )

        # Convert config to JSON
        config_json = config.model_dump(mode="json")

        # Check if config exists
        result = supabase.table("industry_configs").select("id").eq(
            "client_id", client_id
        ).execute()

        if result.data:
            # Update existing
            supabase.table("industry_configs").update({
                "config_data": config_json,
                "source_description": config.source_description,
                "status": "active" if config.is_active else "inactive",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("client_id", client_id).execute()
        else:
            # Insert new
            supabase.table("industry_configs").insert({
                "id": config.config_id,
                "client_id": client_id,
                "config_data": config_json,
                "source_description": config.source_description,
                "status": "active" if config.is_active else "inactive",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()

        # Invalidate cache
        _config_cache.invalidate(client_id)

    except Exception as e:
        raise ConfigLoadError(f"Failed to save config for client {client_id}: {str(e)}")


async def delete_config(client_id: str) -> None:
    """
    Delete the configuration for a client.
    """
    try:
        from supabase import create_client

        settings = get_settings()
        supabase = create_client(
            settings.supabase_url,
            settings.supabase_key.get_secret_value(),
        )

        supabase.table("industry_configs").delete().eq(
            "client_id", client_id
        ).execute()

        # Invalidate cache
        _config_cache.invalidate(client_id)

    except Exception as e:
        raise ConfigLoadError(f"Failed to delete config for client {client_id}: {str(e)}")


# =============================================================================
# Utility Functions
# =============================================================================

def get_config_cache() -> ConfigCache:
    """Get the global config cache instance."""
    return _config_cache


def clear_config_cache() -> None:
    """Clear all cached configurations."""
    _config_cache.clear()


async def get_all_configs() -> list[tuple[str, IndustryConfig]]:
    """
    Get all active configurations.

    Returns a list of (client_id, config) tuples.
    """
    try:
        from supabase import create_client

        settings = get_settings()
        supabase = create_client(
            settings.supabase_url,
            settings.supabase_key.get_secret_value(),
        )

        result = supabase.table("industry_configs").select(
            "client_id, config_data"
        ).eq("status", "active").execute()

        configs = []
        for row in result.data:
            try:
                config = _build_config_from_json(row["config_data"])
                configs.append((row["client_id"], config))
            except Exception:
                continue  # Skip invalid configs

        return configs

    except Exception as e:
        raise ConfigLoadError(f"Failed to load all configs: {str(e)}")


# =============================================================================
# Config Accessors for Pipeline Integration
# =============================================================================

class ConfigAccessor:
    """
    Provides easy access to config properties for pipeline components.

    This class wraps an IndustryConfig and provides convenience methods
    that are commonly needed by collectors, analyzers, and reporters.
    """

    def __init__(self, config: IndustryConfig):
        self.config = config

    @property
    def business_type(self) -> str:
        return self.config.business_type

    @property
    def entity_name(self) -> str:
        return self.config.entity_name

    def get_enabled_sources(self) -> list[DataSourceConfig]:
        """Get all enabled data sources."""
        return self.config.get_enabled_sources()

    def get_source_by_type(self, source_type: DataSourceType) -> Optional[DataSourceConfig]:
        """Get a data source by type."""
        for source in self.config.data_sources:
            if source.source_type == source_type and source.enabled:
                return source
        return None

    def has_source(self, source_type: DataSourceType) -> bool:
        """Check if a source type is enabled."""
        return self.get_source_by_type(source_type) is not None

    def get_kpi_fields(self) -> list[DataFieldConfig]:
        """Get all KPI fields."""
        return self.config.get_kpi_fields()

    def get_field_by_name(self, name: str) -> Optional[DataFieldConfig]:
        """Get a field by name."""
        for field in self.config.custom_fields:
            if field.name == name:
                return field
        return None

    def get_themes(self) -> list[ThemeConfig]:
        """Get all analysis themes."""
        return self.config.themes

    def get_themes_by_category(self) -> dict[str, list[ThemeConfig]]:
        """Get themes grouped by category."""
        return self.config.get_themes_by_category()

    def get_prompt(self, prompt_name: str, default: str = "") -> str:
        """Get a prompt by name."""
        return self.config.get_prompt(prompt_name, default)

    def get_sentiment_prompt(self) -> str:
        """Get the sentiment analysis prompt."""
        default = f"Analyze the following content for a {self.entity_name}."
        return self.config.sentiment_config.custom_prompt or self.get_prompt(
            "sentiment_analysis", default
        )

    def get_insight_prompt(self) -> str:
        """Get the insight generation prompt."""
        default = f"Generate insights for this {self.entity_name}."
        return self.get_prompt("insight_generation", default)

    def get_competitor_config(self) -> Optional[CompetitorConfig]:
        """Get competitor configuration."""
        return self.config.competitor_config

    def should_track_competitors(self) -> bool:
        """Check if competitor tracking is enabled."""
        return self.config.competitor_config is not None

    def get_report_config(self) -> ReportConfig:
        """Get report configuration."""
        return self.config.report_config

    def get_graph_schema(self) -> GraphSchemaConfig:
        """Get the knowledge graph schema."""
        return self.config.graph_schema

    def get_alert_rules(self) -> list[AlertRule]:
        """Get all enabled alert rules."""
        return [r for r in self.config.alert_rules if r.enabled]


async def get_config_accessor(client_id: str) -> ConfigAccessor:
    """
    Get a ConfigAccessor for a client.

    This is the main entry point for pipeline components to access
    configuration.
    """
    config = await load_config(client_id)
    return ConfigAccessor(config)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Exceptions
    "ConfigNotFoundError",
    "ConfigValidationError",
    "ConfigLoadError",
    # Cache
    "ConfigCache",
    "get_config_cache",
    "clear_config_cache",
    # Loaders
    "load_config",
    "load_config_or_default",
    "load_config_sync",
    "save_config",
    "delete_config",
    "get_all_configs",
    # Accessor
    "ConfigAccessor",
    "get_config_accessor",
]
