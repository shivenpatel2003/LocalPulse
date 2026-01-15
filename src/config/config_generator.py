"""
AI-Powered Configuration Generator.

This module uses Claude to intelligently generate complete IndustryConfig
objects from natural language descriptions. It supports:
- Initial config generation from business description
- Iterative refinement through conversation
- Smart defaults based on detected patterns
- Reasoning explanations for all choices

The generator produces production-ready configurations that work with
the entire LocalPulse pipeline.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

import anthropic
from pydantic import BaseModel

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
)
from src.config.settings import get_settings


# =============================================================================
# Session Management
# =============================================================================

class SessionStatus(str, Enum):
    """Status of an onboarding session."""
    NEEDS_MORE_INFO = "needs_more_info"
    CONFIG_READY = "config_ready"
    CONFIRMED = "confirmed"
    ERROR = "error"


@dataclass
class ConversationMessage:
    """A message in the onboarding conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OnboardingSession:
    """Tracks the state of an onboarding conversation."""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    status: SessionStatus = SessionStatus.NEEDS_MORE_INFO
    conversation_history: list[ConversationMessage] = field(default_factory=list)
    current_config: Optional[IndustryConfig] = None
    questions: list[str] = field(default_factory=list)
    generation_reasoning: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self.conversation_history.append(ConversationMessage(role=role, content=content))
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "conversation_history": [
                {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
                for m in self.conversation_history
            ],
            "current_config": self.current_config.model_dump() if self.current_config else None,
            "questions": self.questions,
            "generation_reasoning": self.generation_reasoning,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OnboardingSession":
        """Create session from dictionary."""
        session = cls(
            session_id=data["session_id"],
            status=SessionStatus(data["status"]),
            conversation_history=[
                ConversationMessage(
                    role=m["role"],
                    content=m["content"],
                    timestamp=datetime.fromisoformat(m["timestamp"]),
                )
                for m in data.get("conversation_history", [])
            ],
            questions=data.get("questions", []),
            generation_reasoning=data.get("generation_reasoning", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            error_message=data.get("error_message"),
        )
        if data.get("current_config"):
            session.current_config = IndustryConfig(**data["current_config"])
        return session


# =============================================================================
# Response Models
# =============================================================================

class GeneratorResponse(BaseModel):
    """Response from the config generator."""
    status: SessionStatus
    session_id: str
    config: Optional[IndustryConfig] = None
    questions: list[str] = []
    reasoning: str = ""
    error: Optional[str] = None


# =============================================================================
# Prompt Templates
# =============================================================================

SYSTEM_PROMPT = """You are an expert business intelligence configuration specialist. Your job is to create comprehensive monitoring configurations for ANY type of business based on their description.

You excel at:
1. Understanding diverse business types (retail, services, healthcare, fitness, entertainment, etc.)
2. Identifying relevant data sources (Google reviews, social media, industry-specific platforms)
3. Creating meaningful metrics and KPIs that matter for each business
4. Designing analysis themes that capture what customers care about
5. Configuring competitive intelligence appropriately

When given a business description, you should:
1. First assess if you have enough information to create a complete config
2. If not, ask clarifying questions (maximum 3-4 focused questions)
3. If yes, generate a complete, production-ready configuration

Your configurations must be practical and actionable. Focus on:
- Data sources they can actually access
- Metrics they can realistically track
- Themes relevant to their industry
- Competitor discovery methods that make sense

Be creative but realistic. A dog grooming salon and a TikTok influencer need very different configurations."""

CONFIG_GENERATION_PROMPT = """Based on the conversation so far, generate a complete IndustryConfig for this business.

Business context from conversation:
{conversation_context}

Generate a JSON configuration following this exact schema. Be thorough and creative with the themes and metrics.

IMPORTANT GUIDELINES:
1. Generate 5-10 custom fields covering their key metrics
2. Include 4-8 relevant themes for sentiment analysis
3. Configure appropriate data sources (Google Places for local businesses, social media for influencers, etc.)
4. Create a report structure with 5-7 sections
5. Design a knowledge graph schema that captures their business relationships
6. Write custom prompts tailored to their industry
7. Include at least 2-3 alert rules

Output a JSON object with these top-level keys:
{{
    "config_name": "string - descriptive name",
    "industry_name": "string - broad industry",
    "industry_category": "string - category within industry",
    "business_type": "string - specific business type",
    "entity_name": "string - singular (e.g., 'salon', 'creator')",
    "entity_name_plural": "string - plural form",
    "business_description": "string - detailed description",
    "location": "string or null",
    "market_scope": "local|regional|national|global",
    "target_audience": "string - who their customers are",
    "custom_fields": [...],
    "data_sources": [...],
    "themes": [...],
    "sentiment_config": {{...}},
    "competitor_config": {{...}},
    "report_config": {{...}},
    "graph_schema": {{...}},
    "prompts": {{...}},
    "alert_rules": [...],
    "source_description": "original user input",
    "generation_reasoning": "explain your choices"
}}

For custom_fields, each field should have:
- name (lowercase_with_underscores)
- display_name (Human Readable)
- description
- data_type: number|text|rating|percentage|currency|date|boolean|list
- source_type: api|calculated|manual_input|webhook|csv_import
- source_config: {{}} with relevant config
- aggregation: sum|average|latest|trend|count|min|max
- display_format: e.g., "{{value}}%", "£{{value}}"
- is_kpi: true/false
- track_trend: true/false

For data_sources, include:
- source_type: google_places|instagram|tiktok|twitter|yelp|tripadvisor|custom_api|webhook|manual|csv
- display_name
- enabled: true
- search_config: {{}} with how to find their data
- sync_frequency: realtime|hourly|daily|weekly

For themes, include:
- name (lowercase)
- display_name
- description
- category (group related themes)
- positive_indicators: ["list", "of", "phrases"]
- negative_indicators: ["list", "of", "phrases"]
- weight: 0.0-1.0
- industry_specific: true/false
- suggested_actions: {{"positive": [...], "negative": [...]}}

For competitor_config:
- discovery_method: location_radius|search_terms|manual_list|similar_audience|same_category|hashtag_overlap
- search_config: appropriate for the method
- comparison_metrics: ["list", "of", "field_names"]
- track_their_reviews: true/false
- track_their_social: true/false
- max_competitors: number

For report_config:
- report_name
- tone: professional|casual|technical|executive
- sections: array of section configs
- Each section needs: title, section_type, visualization, ai_generated_content, priority

For graph_schema:
- nodes: [{{"label": "...", "properties": [...]}}]
- relationships: [{{"from_node": "...", "to_node": "...", "relationship_type": "..."}}]
- indexes: ["Node.property"]

For prompts, include keys:
- sentiment_analysis
- insight_generation
- competitor_analysis
- recommendation
- executive_summary

For alert_rules:
- name
- condition (e.g., "google_rating < 4.0")
- severity: info|warning|critical

Output ONLY valid JSON, no markdown or explanation outside the JSON."""

CLARIFICATION_PROMPT = """Based on the business description provided, I need to ask a few clarifying questions to create the best configuration.

Business description:
{description}

Previous conversation:
{conversation_history}

Analyze what we know and what we need to know. Consider:
1. Do we know their specific business type?
2. Do we know what metrics/data matter to them?
3. Do we know if they want competitor tracking?
4. Do we know their location (if relevant)?
5. Do we know what platforms/data sources they use?

If we have enough information to generate a complete, useful configuration, respond with:
{{"status": "ready", "reasoning": "explanation of why we have enough info"}}

If we need more information, respond with:
{{"status": "needs_info", "questions": ["question 1", "question 2", ...], "reasoning": "what we're missing"}}

Maximum 4 questions. Make them specific and actionable.

Output ONLY valid JSON."""

REFINEMENT_PROMPT = """The user wants to refine their configuration.

Current configuration summary:
- Business: {business_type}
- Current fields: {current_fields}
- Current themes: {current_themes}
- Current sources: {current_sources}

User's refinement request:
{refinement}

Generate the changes needed as a JSON object:
{{
    "action": "add|remove|modify",
    "changes": {{
        "custom_fields_to_add": [...],
        "custom_fields_to_remove": ["field_name"],
        "themes_to_add": [...],
        "themes_to_remove": ["theme_name"],
        "data_sources_to_add": [...],
        "data_sources_to_remove": ["source_id"],
        "other_changes": {{}}
    }},
    "reasoning": "explanation"
}}

Output ONLY valid JSON."""


# =============================================================================
# Config Generator
# =============================================================================

class ConfigGenerator:
    """
    AI-powered configuration generator using Claude.

    Generates complete IndustryConfig objects from natural language
    descriptions through a conversational interface.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """Initialize the generator with a specific model."""
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        self.model = model
        self._sessions: dict[str, OnboardingSession] = {}

    def _call_claude(self, messages: list[dict], system: str = SYSTEM_PROMPT) -> str:
        """Make a call to Claude API."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from Claude's response, handling potential formatting."""
        # Try to extract JSON from the response
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines if they're code block markers
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        # Try to parse as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse JSON from response: {text[:500]}")

    def _get_or_create_session(self, session_id: Optional[str] = None) -> OnboardingSession:
        """Get an existing session or create a new one."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        session = OnboardingSession()
        self._sessions[session.session_id] = session
        return session

    def _build_conversation_context(self, session: OnboardingSession) -> str:
        """Build context string from conversation history."""
        if not session.conversation_history:
            return "No previous conversation."

        context = []
        for msg in session.conversation_history:
            context.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(context)

    def _create_config_from_json(self, config_data: dict[str, Any]) -> IndustryConfig:
        """Create an IndustryConfig from parsed JSON data."""
        # Build custom fields
        custom_fields = []
        for field_data in config_data.get("custom_fields", []):
            try:
                custom_fields.append(DataFieldConfig(
                    name=field_data.get("name", ""),
                    display_name=field_data.get("display_name", ""),
                    description=field_data.get("description", ""),
                    data_type=DataType(field_data.get("data_type", "text")),
                    source_type=SourceType(field_data.get("source_type", "manual_input")),
                    source_config=field_data.get("source_config", {}),
                    aggregation=AggregationType(field_data.get("aggregation", "latest")),
                    display_format=field_data.get("display_format", "{value}"),
                    is_kpi=field_data.get("is_kpi", False),
                    track_trend=field_data.get("track_trend", True),
                    alert_thresholds=[
                        AlertThreshold(**t) for t in field_data.get("alert_thresholds", [])
                    ],
                ))
            except Exception:
                continue  # Skip invalid fields

        # Build data sources
        data_sources = []
        for source_data in config_data.get("data_sources", []):
            try:
                auth_config = None
                if source_data.get("auth_config"):
                    auth_config = AuthConfig(**source_data["auth_config"])

                rate_limits = None
                if source_data.get("rate_limits"):
                    rate_limits = RateLimitConfig(**source_data["rate_limits"])

                data_sources.append(DataSourceConfig(
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
                ))
            except Exception:
                continue

        # Build themes
        themes = []
        for theme_data in config_data.get("themes", []):
            try:
                themes.append(ThemeConfig(
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
                ))
            except Exception:
                continue

        # Build competitor config
        competitor_config = None
        if config_data.get("competitor_config"):
            cc = config_data["competitor_config"]
            try:
                competitor_config = CompetitorConfig(
                    discovery_method=CompetitorDiscoveryMethod(
                        cc.get("discovery_method", "location_radius")
                    ),
                    search_config=cc.get("search_config", {}),
                    comparison_metrics=cc.get("comparison_metrics", []),
                    track_their_reviews=cc.get("track_their_reviews", True),
                    track_their_social=cc.get("track_their_social", False),
                    track_their_pricing=cc.get("track_their_pricing", False),
                    max_competitors=cc.get("max_competitors", 10),
                    update_frequency=SyncFrequency(cc.get("update_frequency", "weekly")),
                )
            except Exception:
                pass

        # Build report sections
        sections = []
        report_data = config_data.get("report_config", {})
        for sec_data in report_data.get("sections", []):
            try:
                sections.append(ReportSection(
                    title=sec_data.get("title", ""),
                    description=sec_data.get("description"),
                    section_type=SectionType(sec_data.get("section_type", "custom_metrics")),
                    data_fields=sec_data.get("data_fields", []),
                    visualization=VisualizationType(sec_data.get("visualization", "table")),
                    ai_generated_content=sec_data.get("ai_generated_content", True),
                    priority=sec_data.get("priority", 1),
                ))
            except Exception:
                continue

        # Add default sections if none were generated
        if not sections:
            sections = [
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
                    visualization=VisualizationType.CARDS,
                    priority=2,
                ),
                ReportSection(
                    title="Sentiment Analysis",
                    section_type=SectionType.SENTIMENT_ANALYSIS,
                    visualization=VisualizationType.BAR_CHART,
                    ai_generated_content=True,
                    priority=3,
                ),
                ReportSection(
                    title="Theme Breakdown",
                    section_type=SectionType.THEME_BREAKDOWN,
                    visualization=VisualizationType.PIE_CHART,
                    priority=4,
                ),
                ReportSection(
                    title="Recommendations",
                    section_type=SectionType.RECOMMENDATIONS,
                    visualization=VisualizationType.CARDS,
                    ai_generated_content=True,
                    priority=5,
                ),
            ]

        # Build report config
        delivery_data = report_data.get("delivery", {})
        delivery_config = DeliveryConfig(
            email=delivery_data.get("email"),
            slack=delivery_data.get("slack"),
            webhook=delivery_data.get("webhook"),
            pdf_export=delivery_data.get("pdf_export", True),
        )

        report_config = ReportConfig(
            report_name=report_data.get("report_name", "Weekly Intelligence Report"),
            report_description=report_data.get("report_description"),
            sections=sections,
            tone=ReportTone(report_data.get("tone", "professional")),
            length=ReportLength(report_data.get("length", "standard")),
            include_raw_data=report_data.get("include_raw_data", False),
            include_recommendations=report_data.get("include_recommendations", True),
            include_competitor_intel=report_data.get("include_competitor_intel", True),
            delivery=delivery_config,
        )

        # Build graph schema
        graph_data = config_data.get("graph_schema", {})

        def normalize_properties(props: list) -> list[dict]:
            """Convert string properties to dict format."""
            result = []
            for p in props:
                if isinstance(p, str):
                    result.append({"name": p, "type": "string"})
                elif isinstance(p, dict):
                    result.append(p)
            return result

        nodes = []
        for n in graph_data.get("nodes", []):
            try:
                nodes.append(NodeSchema(
                    label=n.get("label", ""),
                    properties=normalize_properties(n.get("properties", [])),
                ))
            except Exception:
                continue

        relationships = []
        for r in graph_data.get("relationships", []):
            try:
                relationships.append(RelationshipSchema(
                    from_node=r.get("from_node", ""),
                    to_node=r.get("to_node", ""),
                    relationship_type=r.get("relationship_type", ""),
                    properties=normalize_properties(r.get("properties", [])),
                ))
            except Exception:
                continue

        graph_schema = GraphSchemaConfig(
            nodes=nodes,
            relationships=relationships,
            indexes=graph_data.get("indexes", []),
            constraints=graph_data.get("constraints", []),
        )

        # Build alert rules
        alert_rules = []
        for rule_data in config_data.get("alert_rules", []):
            try:
                alert_rules.append(AlertRule(
                    name=rule_data.get("name", ""),
                    description=rule_data.get("description"),
                    condition=rule_data.get("condition", ""),
                    severity=rule_data.get("severity", "warning"),
                    notification_channels=rule_data.get("notification_channels", []),
                    enabled=rule_data.get("enabled", True),
                ))
            except Exception:
                continue

        # Build sentiment config
        sentiment_data = config_data.get("sentiment_config", {})
        sentiment_config = SentimentConfig(
            model=sentiment_data.get("model", "claude-sonnet-4-20250514"),
            include_reasoning=sentiment_data.get("include_reasoning", True),
            confidence_threshold=sentiment_data.get("confidence_threshold", 0.7),
            custom_prompt=sentiment_data.get("custom_prompt"),
        )

        # Create the config
        return IndustryConfig(
            config_name=config_data.get("config_name", "Generated Configuration"),
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
            source_description=config_data.get("source_description", ""),
            generation_reasoning=config_data.get("generation_reasoning", ""),
            created_by="ai_generated",
        )

    async def start_onboarding(self, business_description: str) -> GeneratorResponse:
        """
        Start the onboarding process with an initial business description.

        Returns either clarifying questions or a ready configuration.
        """
        session = self._get_or_create_session()
        session.add_message("user", business_description)

        try:
            # First, check if we need more information
            clarification_response = self._call_claude(
                messages=[{
                    "role": "user",
                    "content": CLARIFICATION_PROMPT.format(
                        description=business_description,
                        conversation_history="",
                    ),
                }],
            )

            result = self._parse_json_response(clarification_response)

            if result.get("status") == "needs_info":
                # We need more information
                questions = result.get("questions", [])
                session.questions = questions
                session.generation_reasoning = result.get("reasoning", "")
                session.status = SessionStatus.NEEDS_MORE_INFO

                # Add assistant message with questions
                question_text = "To create the best configuration for you, I have a few questions:\n"
                question_text += "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
                session.add_message("assistant", question_text)

                return GeneratorResponse(
                    status=SessionStatus.NEEDS_MORE_INFO,
                    session_id=session.session_id,
                    questions=questions,
                    reasoning=result.get("reasoning", ""),
                )
            else:
                # We have enough info, generate the config
                return await self._generate_config(session)

        except Exception as e:
            session.status = SessionStatus.ERROR
            session.error_message = str(e)
            return GeneratorResponse(
                status=SessionStatus.ERROR,
                session_id=session.session_id,
                error=str(e),
            )

    async def continue_onboarding(
        self, session_id: str, answers: str
    ) -> GeneratorResponse:
        """
        Continue the onboarding process with user's answers to questions.
        """
        if session_id not in self._sessions:
            return GeneratorResponse(
                status=SessionStatus.ERROR,
                session_id=session_id,
                error="Session not found",
            )

        session = self._sessions[session_id]
        session.add_message("user", answers)

        try:
            # Check if we now have enough information
            conversation_context = self._build_conversation_context(session)

            clarification_response = self._call_claude(
                messages=[{
                    "role": "user",
                    "content": CLARIFICATION_PROMPT.format(
                        description=session.conversation_history[0].content,
                        conversation_history=conversation_context,
                    ),
                }],
            )

            result = self._parse_json_response(clarification_response)

            if result.get("status") == "needs_info":
                # Still need more info
                questions = result.get("questions", [])
                session.questions = questions
                session.status = SessionStatus.NEEDS_MORE_INFO

                question_text = "I have a few more questions:\n"
                question_text += "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
                session.add_message("assistant", question_text)

                return GeneratorResponse(
                    status=SessionStatus.NEEDS_MORE_INFO,
                    session_id=session.session_id,
                    questions=questions,
                    reasoning=result.get("reasoning", ""),
                )
            else:
                # Generate the config
                return await self._generate_config(session)

        except Exception as e:
            session.status = SessionStatus.ERROR
            session.error_message = str(e)
            return GeneratorResponse(
                status=SessionStatus.ERROR,
                session_id=session.session_id,
                error=str(e),
            )

    async def _generate_config(self, session: OnboardingSession) -> GeneratorResponse:
        """Generate a complete configuration from the session context."""
        conversation_context = self._build_conversation_context(session)

        config_response = self._call_claude(
            messages=[{
                "role": "user",
                "content": CONFIG_GENERATION_PROMPT.format(
                    conversation_context=conversation_context,
                ),
            }],
        )

        config_data = self._parse_json_response(config_response)

        # Add source description from conversation
        config_data["source_description"] = conversation_context

        # Create the IndustryConfig
        config = self._create_config_from_json(config_data)

        # Validate the config
        is_valid, errors = config.validate_config()
        if not is_valid:
            # Try to fix common issues
            if not config.custom_fields:
                config.custom_fields = self._generate_default_fields(config.business_type)
            if not config.themes:
                config.themes = self._generate_default_themes(config.business_type)

        session.current_config = config
        session.status = SessionStatus.CONFIG_READY
        session.generation_reasoning = config.generation_reasoning

        session.add_message(
            "assistant",
            f"I've generated a configuration for your {config.business_type}. "
            f"It includes {len(config.custom_fields)} custom fields, "
            f"{len(config.themes)} analysis themes, and {len(config.data_sources)} data sources."
        )

        return GeneratorResponse(
            status=SessionStatus.CONFIG_READY,
            session_id=session.session_id,
            config=config,
            reasoning=config.generation_reasoning,
        )

    async def refine_config(
        self, session_id: str, refinement: str
    ) -> GeneratorResponse:
        """
        Refine an existing configuration based on user feedback.
        """
        if session_id not in self._sessions:
            return GeneratorResponse(
                status=SessionStatus.ERROR,
                session_id=session_id,
                error="Session not found",
            )

        session = self._sessions[session_id]
        if not session.current_config:
            return GeneratorResponse(
                status=SessionStatus.ERROR,
                session_id=session_id,
                error="No configuration to refine",
            )

        session.add_message("user", refinement)
        config = session.current_config

        try:
            # Ask Claude for the changes
            refinement_response = self._call_claude(
                messages=[{
                    "role": "user",
                    "content": REFINEMENT_PROMPT.format(
                        business_type=config.business_type,
                        current_fields=", ".join(f.name for f in config.custom_fields),
                        current_themes=", ".join(t.name for t in config.themes),
                        current_sources=", ".join(s.display_name for s in config.data_sources),
                        refinement=refinement,
                    ),
                }],
            )

            changes = self._parse_json_response(refinement_response)

            # Apply changes
            self._apply_refinements(config, changes)

            session.current_config = config
            session.generation_reasoning += f"\n\nRefinement: {changes.get('reasoning', '')}"

            session.add_message(
                "assistant",
                f"Configuration updated. {changes.get('reasoning', 'Changes applied.')}"
            )

            return GeneratorResponse(
                status=SessionStatus.CONFIG_READY,
                session_id=session.session_id,
                config=config,
                reasoning=changes.get("reasoning", ""),
            )

        except Exception as e:
            return GeneratorResponse(
                status=SessionStatus.ERROR,
                session_id=session.session_id,
                error=str(e),
            )

    def _apply_refinements(
        self, config: IndustryConfig, changes: dict[str, Any]
    ) -> None:
        """Apply refinement changes to a configuration."""
        change_details = changes.get("changes", {})

        # Add new fields
        for field_data in change_details.get("custom_fields_to_add", []):
            try:
                new_field = DataFieldConfig(
                    name=field_data.get("name", ""),
                    display_name=field_data.get("display_name", ""),
                    description=field_data.get("description", ""),
                    data_type=DataType(field_data.get("data_type", "text")),
                    source_type=SourceType(field_data.get("source_type", "manual_input")),
                    source_config=field_data.get("source_config", {}),
                    aggregation=AggregationType(field_data.get("aggregation", "latest")),
                    display_format=field_data.get("display_format", "{value}"),
                    is_kpi=field_data.get("is_kpi", False),
                    track_trend=field_data.get("track_trend", True),
                )
                config.custom_fields.append(new_field)
            except Exception:
                continue

        # Remove fields
        fields_to_remove = change_details.get("custom_fields_to_remove", [])
        config.custom_fields = [
            f for f in config.custom_fields if f.name not in fields_to_remove
        ]

        # Add new themes
        for theme_data in change_details.get("themes_to_add", []):
            try:
                new_theme = ThemeConfig(
                    name=theme_data.get("name", ""),
                    display_name=theme_data.get("display_name", ""),
                    description=theme_data.get("description", ""),
                    category=theme_data.get("category", "General"),
                    positive_indicators=theme_data.get("positive_indicators", []),
                    negative_indicators=theme_data.get("negative_indicators", []),
                    weight=theme_data.get("weight", 1.0),
                    industry_specific=theme_data.get("industry_specific", False),
                )
                config.themes.append(new_theme)
            except Exception:
                continue

        # Remove themes
        themes_to_remove = change_details.get("themes_to_remove", [])
        config.themes = [t for t in config.themes if t.name not in themes_to_remove]

        # Add new data sources
        for source_data in change_details.get("data_sources_to_add", []):
            try:
                new_source = DataSourceConfig(
                    source_type=DataSourceType(source_data.get("source_type", "manual")),
                    display_name=source_data.get("display_name", ""),
                    enabled=True,
                    search_config=source_data.get("search_config", {}),
                    sync_frequency=SyncFrequency(source_data.get("sync_frequency", "daily")),
                )
                config.data_sources.append(new_source)
            except Exception:
                continue

        # Remove data sources
        sources_to_remove = change_details.get("data_sources_to_remove", [])
        config.data_sources = [
            s for s in config.data_sources if s.source_id not in sources_to_remove
        ]

        # Update timestamp
        config.updated_at = datetime.utcnow()

    def _generate_default_fields(self, business_type: str) -> list[DataFieldConfig]:
        """Generate default fields if none were generated."""
        return [
            DataFieldConfig(
                name="overall_rating",
                display_name="Overall Rating",
                description=f"Average rating for this {business_type}",
                data_type=DataType.RATING,
                source_type=SourceType.CALCULATED,
                aggregation=AggregationType.AVERAGE,
                display_format="{value} ★",
                is_kpi=True,
            ),
            DataFieldConfig(
                name="review_count",
                display_name="Review Count",
                description="Total number of reviews",
                data_type=DataType.NUMBER,
                source_type=SourceType.API,
                aggregation=AggregationType.LATEST,
                is_kpi=True,
            ),
            DataFieldConfig(
                name="sentiment_score",
                display_name="Sentiment Score",
                description="Overall sentiment from reviews",
                data_type=DataType.PERCENTAGE,
                source_type=SourceType.CALCULATED,
                aggregation=AggregationType.AVERAGE,
                display_format="{value}%",
                is_kpi=True,
            ),
        ]

    def _generate_default_themes(self, business_type: str) -> list[ThemeConfig]:
        """Generate default themes if none were generated."""
        return [
            ThemeConfig(
                name="service_quality",
                display_name="Service Quality",
                description="Quality of service provided",
                category="Service",
                positive_indicators=["great service", "helpful", "professional", "friendly"],
                negative_indicators=["poor service", "rude", "unprofessional", "slow"],
                weight=1.0,
            ),
            ThemeConfig(
                name="value",
                display_name="Value for Money",
                description="Perceived value relative to price",
                category="Value",
                positive_indicators=["good value", "worth it", "fair price", "reasonable"],
                negative_indicators=["overpriced", "expensive", "not worth", "waste of money"],
                weight=0.8,
            ),
            ThemeConfig(
                name="overall_experience",
                display_name="Overall Experience",
                description="General customer experience",
                category="Experience",
                positive_indicators=["highly recommend", "will return", "excellent", "amazing"],
                negative_indicators=["never again", "disappointed", "avoid", "terrible"],
                weight=0.9,
            ),
        ]

    def get_session(self, session_id: str) -> Optional[OnboardingSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def get_session_reasoning(self, session_id: str) -> str:
        """Get the reasoning for a session's configuration."""
        session = self._sessions.get(session_id)
        if session and session.current_config:
            return session.current_config.generation_reasoning
        return ""

    def save_session(self, session_id: str) -> dict[str, Any]:
        """Get session data for persistence."""
        session = self._sessions.get(session_id)
        if session:
            return session.to_dict()
        return {}

    def load_session(self, session_data: dict[str, Any]) -> OnboardingSession:
        """Load a session from persisted data."""
        session = OnboardingSession.from_dict(session_data)
        self._sessions[session.session_id] = session
        return session


# =============================================================================
# Singleton Instance
# =============================================================================

_generator_instance: Optional[ConfigGenerator] = None


def get_config_generator() -> ConfigGenerator:
    """Get the singleton config generator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ConfigGenerator()
    return _generator_instance


# =============================================================================
# Convenience Functions
# =============================================================================

async def generate_config_from_description(description: str) -> IndustryConfig:
    """
    One-shot config generation from a business description.

    This is a convenience function that attempts to generate a complete
    configuration without the conversational flow. It may produce less
    optimal results for complex business types.
    """
    generator = get_config_generator()
    response = await generator.start_onboarding(description)

    if response.status == SessionStatus.CONFIG_READY and response.config:
        return response.config
    elif response.status == SessionStatus.NEEDS_MORE_INFO:
        # Try to generate anyway with available info
        session = generator.get_session(response.session_id)
        if session:
            # Force generation
            return await generator._generate_config(session)

    raise ValueError(f"Could not generate configuration: {response.error or 'Unknown error'}")


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "SessionStatus",
    "ConversationMessage",
    "OnboardingSession",
    "GeneratorResponse",
    "ConfigGenerator",
    "get_config_generator",
    "generate_config_from_description",
]
