#!/usr/bin/env python3
"""
Comprehensive Test Script for Dynamic Industry Configuration System.

This script tests the AI-powered configuration generation with 3 very
different business types to demonstrate the flexibility of the system.

Test Cases:
1. Dog Grooming Salon (Local Service)
2. TikTok Fitness Influencer (Creator/Influencer)
3. Plumbing Business (Home Services)

Usage:
    python scripts/test_config_generator.py

    # Test specific business type
    python scripts/test_config_generator.py --business grooming

    # Show verbose output
    python scripts/test_config_generator.py --verbose

    # Test the API endpoints
    python scripts/test_config_generator.py --api
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Any

# Add project root to path
sys.path.insert(0, ".")


# =============================================================================
# Test Cases
# =============================================================================

TEST_BUSINESSES = {
    "grooming": {
        "name": "Dog Grooming Salon",
        "description": "I run a dog grooming salon in Leeds. We want to track Google reviews and see how we compare to competitors. We also want to track rebooking rates and customer satisfaction scores.",
        "follow_up": """Our salon is called "Pawfect Grooming Leeds". We offer full grooming, nail trimming,
        teeth cleaning, and puppy first groom services. We collect satisfaction scores via a simple
        post-appointment survey. Please find competitors automatically - top 5 in Leeds area.
        We're also on Facebook and Instagram. Track Google reviews primarily. Weekly reports please.""",
        "expected_sources": ["google_places"],
        "expected_themes": ["service_quality", "pet_handling", "value"],
    },
    "influencer": {
        "name": "TikTok Fitness Influencer",
        "description": "I'm a TikTok fitness influencer with 50k followers. I want to track my engagement rates, follower growth, and how I compare to similar creators. I post workout videos and nutrition tips.",
        "follow_up": """I'm @FitWithSarah on TikTok and Instagram. I do HIIT and home workouts.
        I monetize through brand partnerships and an online coaching program. Main goal is growing engagement
        and tracking which content performs best. Compare me to similar fitness creators in the UK with
        30k-100k followers. Also track Instagram since I cross-post there. Weekly reports.""",
        "expected_sources": ["tiktok", "instagram"],
        "expected_themes": ["content_quality", "engagement", "authenticity"],
    },
    "plumbing": {
        "name": "Plumbing Business",
        "description": "I own a plumbing business in Manchester. I want to track Google reviews, response time reputation, and quote conversion rates. We handle emergency repairs and bathroom installations.",
        "follow_up": """Business name is "Manchester Pro Plumbing". We use a simple spreadsheet for tracking
        quotes and conversions - I'll input that data manually. Main competitors are Aspect Plumbing,
        DrainTech Manchester, and 24/7 Plumbers Manchester. Focus on Google reviews and Checkatrade ratings.
        Also track Trustpilot. We want to know when reviews mention response time or pricing. Weekly reports.""",
        "expected_sources": ["google_places"],
        "expected_themes": ["reliability", "pricing", "professionalism"],
    },
}


# =============================================================================
# Test Functions
# =============================================================================

def print_header(text: str, char: str = "=") -> None:
    """Print a formatted header."""
    line = char * 70
    print(f"\n{line}")
    print(f" {text}")
    print(f"{line}\n")


def print_subheader(text: str) -> None:
    """Print a formatted subheader."""
    print(f"\n--- {text} ---\n")


def print_config_summary(config: Any) -> None:
    """Print a summary of a generated configuration."""
    print(f"Config ID: {config.config_id}")
    print(f"Name: {config.config_name}")
    print(f"Industry: {config.industry_name} / {config.industry_category}")
    print(f"Business Type: {config.business_type}")
    print(f"Entity: {config.entity_name} (plural: {config.entity_name_plural})")
    print(f"Market Scope: {config.market_scope.value}")

    print_subheader("Custom Fields")
    for field in config.custom_fields:
        kpi_marker = " [KPI]" if field.is_kpi else ""
        print(f"  - {field.display_name}{kpi_marker}")
        print(f"    Type: {field.data_type.value}, Source: {field.source_type.value}")
        print(f"    Format: {field.display_format}")

    print_subheader("Data Sources")
    for source in config.data_sources:
        enabled = "Enabled" if source.enabled else "Disabled"
        print(f"  - {source.display_name} ({source.source_type.value}) - {enabled}")
        print(f"    Sync: {source.sync_frequency.value}")

    print_subheader("Analysis Themes")
    for theme in config.themes:
        print(f"  - {theme.display_name} ({theme.category})")
        print(f"    Weight: {theme.weight}")
        print(f"    Positive: {', '.join(theme.positive_indicators[:3])}...")
        print(f"    Negative: {', '.join(theme.negative_indicators[:3])}...")

    print_subheader("Competitor Config")
    if config.competitor_config:
        print(f"  Method: {config.competitor_config.discovery_method.value}")
        print(f"  Max Competitors: {config.competitor_config.max_competitors}")
        print(f"  Track Reviews: {config.competitor_config.track_their_reviews}")
        print(f"  Track Social: {config.competitor_config.track_their_social}")
        print(f"  Comparison Metrics: {', '.join(config.competitor_config.comparison_metrics)}")
    else:
        print("  Not configured")

    print_subheader("Report Configuration")
    print(f"  Name: {config.report_config.report_name}")
    print(f"  Tone: {config.report_config.tone.value}")
    print(f"  Length: {config.report_config.length.value}")
    print(f"  Sections: {len(config.report_config.sections)}")
    for section in sorted(config.report_config.sections, key=lambda s: s.priority):
        print(f"    {section.priority}. {section.title} ({section.section_type.value})")

    print_subheader("Knowledge Graph Schema")
    print(f"  Nodes: {', '.join(n.label for n in config.graph_schema.nodes)}")
    print(f"  Relationships: {len(config.graph_schema.relationships)}")
    for rel in config.graph_schema.relationships:
        print(f"    ({rel.from_node})-[{rel.relationship_type}]->({rel.to_node})")

    print_subheader("AI Prompts")
    for name, prompt in config.prompts.items():
        preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
        print(f"  {name}: {preview}")

    print_subheader("Alert Rules")
    for rule in config.alert_rules:
        print(f"  - {rule.name} ({rule.severity})")
        print(f"    Condition: {rule.condition}")


async def test_config_generator_direct(business_key: str, verbose: bool = False) -> None:
    """Test the config generator directly (not through API)."""
    from src.config.config_generator import ConfigGenerator, SessionStatus

    business = TEST_BUSINESSES[business_key]
    print_header(f"Testing: {business['name']}")

    print(f"Description: {business['description']}\n")

    generator = ConfigGenerator()

    # Start onboarding
    print("Starting onboarding...")
    response = await generator.start_onboarding(business["description"])

    print(f"Status: {response.status.value}")
    print(f"Session ID: {response.session_id}")

    if response.status == SessionStatus.NEEDS_MORE_INFO:
        print("\nClarifying Questions:")
        for i, question in enumerate(response.questions, 1):
            print(f"  {i}. {question}")

        # Provide business-specific follow-up answers
        print("\nProviding detailed answers...")
        additional_info = business.get("follow_up", f"""
        We focus on quality service and customer satisfaction.
        Our main competitors are other local {business['name'].lower()}s in the area.
        We want weekly reports sent to the owner.
        Track both online presence and customer feedback.
        """)
        response = await generator.continue_onboarding(
            response.session_id, additional_info
        )
        print(f"Updated Status: {response.status.value}")

    # If still needs info, try one more time with explicit request to generate
    if response.status == SessionStatus.NEEDS_MORE_INFO:
        print("\nProviding final context to generate config...")
        response = await generator.continue_onboarding(
            response.session_id,
            "That's all the information I have. Please generate the best configuration you can with this info."
        )
        print(f"Final Status: {response.status.value}")

    if response.status == SessionStatus.CONFIG_READY:
        config = response.config
        print("\nConfiguration generated successfully!")

        if verbose:
            print_config_summary(config)
        else:
            print(f"\n  Config Name: {config.config_name}")
            print(f"  Custom Fields: {len(config.custom_fields)}")
            print(f"  Data Sources: {len(config.data_sources)}")
            print(f"  Themes: {len(config.themes)}")
            print(f"  Report Sections: {len(config.report_config.sections)}")
            print(f"  Alert Rules: {len(config.alert_rules)}")

        # Validate the config
        is_valid, errors = config.validate_config()
        print(f"\n  Validation: {'PASSED' if is_valid else 'FAILED'}")
        if errors:
            for error in errors:
                print(f"    - {error}")

        # Show reasoning
        print(f"\n  Reasoning: {response.reasoning[:200]}...")

        return config

    elif response.status == SessionStatus.ERROR:
        print(f"\nError: {response.error}")
        return None


async def test_refinement(verbose: bool = False) -> None:
    """Test the configuration refinement flow."""
    from src.config.config_generator import ConfigGenerator, SessionStatus

    print_header("Testing Configuration Refinement")

    generator = ConfigGenerator()

    # Create initial config
    print("Creating initial config for a bakery...")
    response = await generator.start_onboarding(
        "I run a small bakery in London. We want to track reviews and see how we compare to other bakeries."
    )

    # Continue if needed
    if response.status == SessionStatus.NEEDS_MORE_INFO:
        response = await generator.continue_onboarding(
            response.session_id,
            "We sell artisan bread and pastries. We're active on Instagram."
        )

    if response.status != SessionStatus.CONFIG_READY:
        print("Failed to generate initial config")
        return

    print(f"Initial config generated with {len(response.config.custom_fields)} fields")

    # Refinement 1: Add a field
    print("\nRefinement 1: Adding average order value field...")
    response = await generator.refine_config(
        response.session_id,
        "Also add a field to track average order value and daily customer count"
    )

    if response.config:
        print(f"Config now has {len(response.config.custom_fields)} fields")

    # Refinement 2: Remove a theme
    print("\nRefinement 2: Removing a theme...")
    if response.config and response.config.themes:
        theme_to_remove = response.config.themes[0].name
        response = await generator.refine_config(
            response.session_id,
            f"Remove the {theme_to_remove} theme, it's not relevant"
        )

        if response.config:
            print(f"Config now has {len(response.config.themes)} themes")

    # Refinement 3: Add data source
    print("\nRefinement 3: Adding Instagram as a data source...")
    response = await generator.refine_config(
        response.session_id,
        "Add Instagram tracking - we post daily content"
    )

    if response.config:
        print(f"Config now has {len(response.config.data_sources)} data sources")

    print("\nRefinement test complete!")

    if verbose and response.config:
        print_config_summary(response.config)


async def test_schema_validation() -> None:
    """Test the IndustryConfig schema validation."""
    from src.config.industry_schema import (
        IndustryConfig,
        DataFieldConfig,
        DataSourceConfig,
        ThemeConfig,
        ReportConfig,
        ReportSection,
        DataType,
        SourceType,
        DataSourceType,
        SyncFrequency,
        SectionType,
        VisualizationType,
        ReportTone,
        ReportLength,
        MarketScope,
    )

    print_header("Testing Schema Validation")

    # Test 1: Valid minimal config
    print("Test 1: Creating valid minimal config...")
    try:
        config = IndustryConfig(
            config_name="Test Config",
            industry_name="Test Industry",
            industry_category="Test Category",
            business_type="Test Business",
            entity_name="business",
            entity_name_plural="businesses",
            custom_fields=[
                DataFieldConfig(
                    name="test_field",
                    display_name="Test Field",
                    description="A test field",
                    data_type=DataType.NUMBER,
                    source_type=SourceType.MANUAL_INPUT,
                )
            ],
            data_sources=[
                DataSourceConfig(
                    source_type=DataSourceType.MANUAL,
                    display_name="Manual Input",
                    sync_frequency=SyncFrequency.DAILY,
                )
            ],
            themes=[
                ThemeConfig(
                    name="test_theme",
                    display_name="Test Theme",
                    description="A test theme",
                    category="General",
                    positive_indicators=["good"],
                    negative_indicators=["bad"],
                )
            ],
            report_config=ReportConfig(
                report_name="Test Report",
                tone=ReportTone.PROFESSIONAL,
                length=ReportLength.STANDARD,
                sections=[
                    ReportSection(
                        title="Summary",
                        section_type=SectionType.EXECUTIVE_SUMMARY,
                        visualization=VisualizationType.CARDS,
                    )
                ],
            ),
            source_description="Test config",
        )
        is_valid, errors = config.validate_config()
        print(f"  Result: {'PASSED' if is_valid else 'FAILED'}")
        if errors:
            for error in errors:
                print(f"  Error: {error}")
    except Exception as e:
        print(f"  Exception: {e}")

    # Test 2: Invalid config (missing fields)
    print("\nTest 2: Testing validation with empty fields...")
    try:
        config = IndustryConfig(
            config_name="Invalid Config",
            industry_name="Test",
            industry_category="Test",
            business_type="Test",
            entity_name="test",
            entity_name_plural="tests",
            custom_fields=[],  # Empty - should fail
            data_sources=[],   # Empty - should fail
            themes=[],         # Empty - should fail
            report_config=ReportConfig(
                report_name="Test",
                sections=[],   # Empty - should fail
            ),
            source_description="Invalid test",
        )
        is_valid, errors = config.validate_config()
        print(f"  Validation caught {len(errors)} errors:")
        for error in errors:
            print(f"    - {error}")
    except Exception as e:
        print(f"  Exception caught: {e}")


async def test_adapters() -> None:
    """Test the dynamic config adapters."""
    from src.config.industry_schema import create_restaurant_template
    from src.config.dynamic_adapter import get_adapters

    print_header("Testing Configuration Adapters")

    # Create a restaurant config
    config = create_restaurant_template()
    adapters = get_adapters(config)

    print("Testing CollectorAdapter...")
    print(f"  Should collect Google Places: {adapters.collector.should_collect_google_places()}")
    print(f"  Should collect Instagram: {adapters.collector.should_collect_instagram()}")
    google_config = adapters.collector.get_google_places_config()
    print(f"  Google Places config: {google_config}")

    print("\nTesting AnalyzerAdapter...")
    prompt = adapters.analyzer.get_sentiment_prompt()
    print(f"  Sentiment prompt preview: {prompt[:100]}...")
    themes = adapters.analyzer.get_themes()
    print(f"  Themes: {[t.display_name for t in themes]}")
    weights = adapters.analyzer.get_theme_weights()
    print(f"  Theme weights: {weights}")

    print("\nTesting ReportAdapter...")
    print(f"  Report name: {adapters.reporter.get_report_name()}")
    print(f"  Report tone: {adapters.reporter.get_report_tone()}")
    sections = adapters.reporter.get_sections()
    print(f"  Sections: {[s['title'] for s in sections]}")
    kpis = adapters.reporter.get_kpis_for_report()
    print(f"  KPIs: {[k['display_name'] for k in kpis]}")

    print("\nTesting GraphAdapter...")
    print(f"  Node labels: {adapters.graph.get_node_labels()}")
    print(f"  Relationship types: {adapters.graph.get_relationship_types()}")


async def compare_configs() -> None:
    """Generate and compare configs for all test businesses."""
    from src.config.config_generator import ConfigGenerator, SessionStatus

    print_header("Comparing Generated Configurations")

    generator = ConfigGenerator()
    configs = {}

    for key, business in TEST_BUSINESSES.items():
        print(f"\nGenerating config for: {business['name']}...")

        response = await generator.start_onboarding(business["description"])

        if response.status == SessionStatus.NEEDS_MORE_INFO:
            # Use business-specific follow-up
            follow_up = business.get("follow_up", "Track reviews and competitors. Weekly reports.")
            response = await generator.continue_onboarding(
                response.session_id,
                follow_up
            )

        # If still needs info, try once more
        if response.status == SessionStatus.NEEDS_MORE_INFO:
            response = await generator.continue_onboarding(
                response.session_id,
                "Generate the configuration with the information provided."
            )

        if response.status == SessionStatus.CONFIG_READY and response.config:
            configs[key] = response.config
            print(f"  Generated: {len(response.config.custom_fields)} fields, "
                  f"{len(response.config.themes)} themes, "
                  f"{len(response.config.data_sources)} sources")
        else:
            print(f"  Failed: {response.status.value}")

    print_header("Configuration Comparison")

    # Compare field types
    print("\nFields by Business:")
    for key, config in configs.items():
        print(f"\n  {TEST_BUSINESSES[key]['name']}:")
        for field in config.custom_fields[:5]:
            print(f"    - {field.display_name} ({field.data_type.value})")

    # Compare themes
    print("\nThemes by Business:")
    for key, config in configs.items():
        print(f"\n  {TEST_BUSINESSES[key]['name']}:")
        for theme in config.themes[:5]:
            print(f"    - {theme.display_name} ({theme.category})")

    # Compare data sources
    print("\nData Sources by Business:")
    for key, config in configs.items():
        print(f"\n  {TEST_BUSINESSES[key]['name']}:")
        for source in config.data_sources:
            print(f"    - {source.source_type.value}")

    return configs


async def test_api_endpoints() -> None:
    """Test the onboarding API endpoints (requires running server)."""
    print_header("Testing API Endpoints")

    try:
        import httpx

        BASE_URL = "http://127.0.0.1:8000"
        API_URL = f"{BASE_URL}/api/v1/onboard"

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Test 1: Start onboarding
            print("Test 1: POST /api/v1/onboard/start")
            response = await client.post(
                f"{API_URL}/start",
                json={
                    "business_description": TEST_BUSINESSES["grooming"]["description"]
                }
            )
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                session_id = data["session_id"]
                print(f"  Session ID: {session_id}")
                print(f"  Status: {data['status']}")

                if data["status"] == "needs_more_info":
                    print(f"  Questions: {data['questions']}")

                    # Test 2: Continue onboarding
                    print("\nTest 2: POST /api/v1/onboard/continue")
                    response = await client.post(
                        f"{API_URL}/continue",
                        json={
                            "session_id": session_id,
                            "answers": "Track Google reviews and local competitors. Weekly reports."
                        }
                    )
                    print(f"  Status: {response.status_code}")
                    data = response.json()
                    print(f"  Response status: {data['status']}")

                if data.get("config_preview"):
                    print(f"  Config preview: {json.dumps(data['config_preview'], indent=2)[:500]}...")

                    # Test 3: Get explanation
                    print("\nTest 3: GET /api/v1/onboard/{session_id}/explain")
                    response = await client.get(f"{API_URL}/{session_id}/explain")
                    print(f"  Status: {response.status_code}")
                    if response.status_code == 200:
                        explain_data = response.json()
                        print(f"  Business type: {explain_data['business_type']}")
                        print(f"  Field count: {len(explain_data['field_explanations'])}")

                    # Test 4: Refine
                    print("\nTest 4: POST /api/v1/onboard/refine")
                    response = await client.post(
                        f"{API_URL}/refine",
                        json={
                            "session_id": session_id,
                            "refinement": "Add a field to track grooming appointment rebooking rate"
                        }
                    )
                    print(f"  Status: {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        print(f"  Updated config fields: {len(data['config_preview'].get('custom_fields', []))}")

            else:
                print(f"  Error: {response.text}")

    except httpx.ConnectError:
        print("  Error: Could not connect to server. Make sure the API is running:")
        print("    uvicorn src.api.main:app --reload")
    except Exception as e:
        print(f"  Error: {e}")


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="Test the Dynamic Industry Configuration System"
    )
    parser.add_argument(
        "--business", "-b",
        choices=["grooming", "influencer", "plumbing", "all"],
        default="all",
        help="Business type to test"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Test API endpoints (requires running server)"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare configs for all business types"
    )
    parser.add_argument(
        "--refinement",
        action="store_true",
        help="Test the refinement flow"
    )
    parser.add_argument(
        "--validation",
        action="store_true",
        help="Test schema validation"
    )
    parser.add_argument(
        "--adapters",
        action="store_true",
        help="Test configuration adapters"
    )

    args = parser.parse_args()

    print_header("LocalPulse Dynamic Configuration System Test")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        if args.api:
            await test_api_endpoints()

        elif args.compare:
            await compare_configs()

        elif args.refinement:
            await test_refinement(args.verbose)

        elif args.validation:
            await test_schema_validation()

        elif args.adapters:
            await test_adapters()

        elif args.business == "all":
            for key in TEST_BUSINESSES:
                await test_config_generator_direct(key, args.verbose)
        else:
            await test_config_generator_direct(args.business, args.verbose)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print_header("Test Complete")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
