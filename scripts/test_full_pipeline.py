#!/usr/bin/env python3
"""
Full Pipeline Integration Test.

Tests the complete LocalPulse analysis → report pipeline using mock review
data for a dog groomer, real Claude API calls for analysis, and the existing
report template for HTML output.

Phases tested:
1. Analysis  — sentiment, themes, competitors, insights, recommendations
               (calls analysis_graph node functions directly, skipping Neo4j fetch)
2. Reporting — executive summary, chart data, HTML render
               (calls report_graph node functions directly, skipping SendGrid)
3. Review Responses — AI responses for each review via ReviewResponseGenerator

Usage:
    python scripts/test_full_pipeline.py
    python scripts/test_full_pipeline.py --verbose
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, ".")


# =============================================================================
# Mock Data
# =============================================================================

BUSINESS_NAME = "Pawfect Grooming Leeds"
BUSINESS_RATING = 4.4
BUSINESS_TYPE = "dog grooming salon"
GOOGLE_PLACE_ID = "ChIJexampleGroomer123"

MOCK_REVIEWS = [
    {
        "id": str(uuid4()),
        "author_name": "Emma",
        "rating": 5,
        "text": (
            "Absolutely love Pawfect Grooming! My cockapoo Bella always comes out "
            "looking gorgeous. The staff are so gentle with her and she actually "
            "enjoys going now. The puppy first groom package was brilliant."
        ),
        "platform": "google",
        "review_time": "2026-01-25",
    },
    {
        "id": str(uuid4()),
        "author_name": "James",
        "rating": 2,
        "text": (
            "Booked a 10am appointment but wasn't seen until 10:45. Then the groom "
            "took over 2 hours when I was told 90 minutes. The actual grooming was "
            "okay but the wait and lack of communication was really frustrating."
        ),
        "platform": "google",
        "review_time": "2026-01-23",
    },
    {
        "id": str(uuid4()),
        "author_name": "Sophie",
        "rating": 4,
        "text": (
            "Really friendly team and my spaniel looked great afterwards. Only "
            "minor issue was the price — a bit more than I expected for a basic "
            "wash and trim. Would still recommend though."
        ),
        "platform": "google",
        "review_time": "2026-01-22",
    },
    {
        "id": str(uuid4()),
        "author_name": "Mike",
        "rating": 5,
        "text": (
            "First time bringing our rescue greyhound and the staff were amazing. "
            "So patient and gentle with him. The shop was spotless too. Will "
            "definitely be back!"
        ),
        "platform": "google",
        "review_time": "2026-01-21",
    },
    {
        "id": str(uuid4()),
        "author_name": "Aisha",
        "rating": 3,
        "text": (
            "The grooming itself was fine but I had to wait 20 minutes past my "
            "appointment time. Staff were friendly once I was seen though. Clean "
            "premises. Would try again if they sort the scheduling."
        ),
        "platform": "google",
        "review_time": "2026-01-20",
    },
    {
        "id": str(uuid4()),
        "author_name": "Rachel",
        "rating": 5,
        "text": (
            "My border collie has a tricky double coat and they did an incredible "
            "job. Deshedding was thorough, he looks and feels so much better. The "
            "groomer explained exactly what she was doing and gave aftercare tips."
        ),
        "platform": "google",
        "review_time": "2026-01-18",
    },
    {
        "id": str(uuid4()),
        "author_name": "Tom",
        "rating": 4,
        "text": (
            "Good grooming, my golden retriever came back looking smart. Handy "
            "location too. Only thing is parking is tricky on that street. "
            "Affordable prices for the quality."
        ),
        "platform": "google",
        "review_time": "2026-01-17",
    },
    {
        "id": str(uuid4()),
        "author_name": "Chloe",
        "rating": 5,
        "text": (
            "Best dog groomer in Leeds! My poodle mix always looks fantastic. "
            "They use great products and the nail trimming was quick and stress-free. "
            "Lovely welcoming atmosphere. Can't recommend highly enough."
        ),
        "platform": "google",
        "review_time": "2026-01-15",
    },
]

MOCK_COMPETITORS = [
    {
        "name": "Barks & Bubbles Leeds",
        "rating": 4.2,
        "address": "12 High Street, Leeds LS1",
        "primary_type": "pet grooming",
    },
    {
        "name": "Doggy Style Grooming",
        "rating": 4.6,
        "address": "88 Chapel Allerton, Leeds LS7",
        "primary_type": "dog grooming",
    },
    {
        "name": "Muddy Paws Parlour",
        "rating": 3.9,
        "address": "45 Headingley Lane, Leeds LS6",
        "primary_type": "pet grooming",
    },
]


# =============================================================================
# Display Helpers
# =============================================================================

def print_header(text: str, char: str = "=") -> None:
    line = char * 70
    print(f"\n{line}")
    print(f" {text}")
    print(f"{line}")


def print_step(num: int, name: str) -> None:
    print(f"\n  [{num}/7] {name}...")


# =============================================================================
# Pipeline Runner
# =============================================================================

async def run_analysis_phase(verbose: bool = False) -> dict:
    """Run the 5 analysis steps (skipping fetch_data)."""
    from src.graphs.analysis_graph import (
        analyze_sentiment,
        extract_themes,
        compare_competitors,
        generate_insights,
        generate_recommendations,
    )

    # Build initial state as if fetch_data had returned
    state = {
        "business_id": GOOGLE_PLACE_ID,
        "reviews": MOCK_REVIEWS,
        "sentiment_results": {
            "business_name": BUSINESS_NAME,
            "business_rating": BUSINESS_RATING,
            "review_count": len(MOCK_REVIEWS),
        },
        "competitor_analysis": {
            "competitors": MOCK_COMPETITORS,
            "business_name": BUSINESS_NAME,
            "business_rating": BUSINESS_RATING,
        },
        "theme_results": [],
        "insights": [],
        "recommendations": [],
        "errors": [],
        "status": "analyzing",
    }

    steps = [
        ("Sentiment Analysis", analyze_sentiment),
        ("Theme Extraction", extract_themes),
        ("Competitor Comparison", compare_competitors),
        ("Insight Generation", generate_insights),
        ("Recommendation Generation", generate_recommendations),
    ]

    for i, (label, fn) in enumerate(steps, start=1):
        print_step(i, label)
        t0 = time.time()
        update = await fn(state)
        elapsed = time.time() - t0

        # Merge update into state (respecting list reducers)
        for key, value in update.items():
            if key in ("insights", "recommendations", "theme_results", "errors") and isinstance(value, list):
                state[key] = state.get(key, []) + value
            else:
                state[key] = value

        print(f"         Done ({elapsed:.1f}s)")

        if verbose:
            _print_step_detail(label, state)

    return state


def _print_step_detail(label: str, state: dict) -> None:
    """Print extra detail after an analysis step."""
    if label == "Sentiment Analysis":
        s = state.get("sentiment_results", {})
        print(f"         Score: {s.get('overall_score', '?')}, "
              f"Positive: {s.get('positive_count', '?')}, "
              f"Negative: {s.get('negative_count', '?')}, "
              f"Trend: {s.get('trend', '?')}")
    elif label == "Theme Extraction":
        td = state.get("theme_results", [{}])[0] if state.get("theme_results") else {}
        strengths = td.get("top_strengths", [])
        weaknesses = td.get("top_weaknesses", [])
        print(f"         Strengths: {strengths}")
        print(f"         Weaknesses: {weaknesses}")
    elif label == "Competitor Comparison":
        c = state.get("competitor_analysis", {})
        print(f"         Position: {c.get('market_position', '?')}")
        print(f"         Advantages: {c.get('competitive_advantages', [])[:2]}")
    elif label == "Insight Generation":
        for ins in state.get("insights", [])[:3]:
            print(f"         - {ins[:80]}...")
    elif label == "Recommendation Generation":
        for rec in state.get("recommendations", [])[:3]:
            print(f"         - {rec[:80]}...")


async def run_report_phase(analysis_state: dict, verbose: bool = False) -> str:
    """Run the report generation steps (skipping send_email)."""
    from src.graphs.report_graph import (
        prepare_report_data,
        generate_executive_summary,
        create_charts_data,
        render_html_report,
    )

    # Build ReportState
    report_state = {
        "business_id": GOOGLE_PLACE_ID,
        "analysis": analysis_state,
        "report_html": "",
        "report_data": {},
        "email_sent": False,
        "errors": [],
        "status": "pending",
    }

    report_steps = [
        ("Prepare Report Data", prepare_report_data),
        ("Generate Executive Summary", generate_executive_summary),
        ("Create Chart Data", create_charts_data),
        ("Render HTML Report", render_html_report),
    ]

    step_offset = 6  # Steps 6-9 in overall numbering
    for i, (label, fn) in enumerate(report_steps):
        print_step(step_offset + i, label)
        t0 = time.time()
        update = await fn(report_state)
        elapsed = time.time() - t0

        for key, value in update.items():
            if key == "errors" and isinstance(value, list):
                report_state[key] = report_state.get(key, []) + value
            else:
                report_state[key] = value

        print(f"         Done ({elapsed:.1f}s)")

        if verbose and label == "Generate Executive Summary":
            rd = report_state.get("report_data", {})
            print(f"         Headline: {rd.get('headline', 'N/A')}")
            print(f"         Key Metric: {rd.get('key_metric', 'N/A')}")

    return report_state.get("report_html", "")


async def run_review_responses(verbose: bool = False) -> list[dict]:
    """Generate AI responses for every review."""
    from src.services.response_generator import ReviewResponseGenerator, ReviewInput

    generator = ReviewResponseGenerator()
    results = []

    for review in MOCK_REVIEWS:
        inp = ReviewInput(
            reviewer_name=review["author_name"],
            rating=float(review["rating"]),
            review_text=review["text"],
            business_name=BUSINESS_NAME,
            business_type=BUSINESS_TYPE,
        )
        resp = await generator.generate_response(inp)
        results.append({
            "reviewer_name": review["author_name"],
            "rating": review["rating"],
            "review_text": review["text"],
            "ai_response": resp.response_text,
            "tone": resp.tone_used.value,
            "strategy": resp.strategy.value,
        })
        if verbose:
            stars = int(review["rating"])
            print(f"         {'*' * stars}{'.' * (5 - stars)} {review['author_name']}: "
                  f"{resp.response_text[:60]}...")

    return results


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Test the full LocalPulse pipeline")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    print_header("LocalPulse Full Pipeline Test")
    print(f"  Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Business: {BUSINESS_NAME}")
    print(f"  Reviews:  {len(MOCK_REVIEWS)} mock reviews")
    print(f"  Competitors: {len(MOCK_COMPETITORS)} mock competitors")
    print(f"  API: Real Anthropic (Claude) for all AI steps")

    total_t0 = time.time()

    # ── Phase 1: Analysis ────────────────────────────────────────────
    print_header("Phase 1: Analysis (5 Claude calls)", char="-")
    analysis_state = await run_analysis_phase(verbose=args.verbose)

    analysis_ok = analysis_state.get("status") == "completed"
    print(f"\n  Analysis status: {'PASS' if analysis_ok else 'FAIL'}")

    # ── Phase 2: Report ──────────────────────────────────────────────
    print_header("Phase 2: Report Generation (1 Claude call + render)", char="-")
    report_html = await run_report_phase(analysis_state, verbose=args.verbose)

    report_ok = len(report_html) > 5000
    print(f"\n  Report status: {'PASS' if report_ok else 'FAIL'} ({len(report_html):,} chars)")

    # ── Phase 3: Review Responses ────────────────────────────────────
    print_header("Phase 3: Review Responses (8 Claude calls)", char="-")
    print(f"\n  Generating AI responses for all {len(MOCK_REVIEWS)} reviews...")
    responses = await run_review_responses(verbose=args.verbose)

    responses_ok = len(responses) == len(MOCK_REVIEWS)
    print(f"\n  Responses status: {'PASS' if responses_ok else 'FAIL'} ({len(responses)}/{len(MOCK_REVIEWS)})")

    # ── Save HTML ────────────────────────────────────────────────────
    print_header("Output Files", char="-")

    report_path = Path("/tmp/localpulse_full_report.html")
    report_path.write_text(report_html, encoding="utf-8")
    print(f"  Full report:      {report_path}  ({report_path.stat().st_size:,} bytes)")

    # Build a combined HTML with report + review responses appended
    combined_html = _build_combined_report(report_html, responses)
    combined_path = Path("/tmp/localpulse_full_report_with_responses.html")
    combined_path.write_text(combined_html, encoding="utf-8")
    print(f"  Report+Responses: {combined_path}  ({combined_path.stat().st_size:,} bytes)")

    # ── Summary ──────────────────────────────────────────────────────
    elapsed = time.time() - total_t0
    print_header("Results")

    sentiment = analysis_state.get("sentiment_results", {})
    print(f"  Sentiment Score:    {sentiment.get('overall_score', 'N/A')}")
    print(f"  Trend:              {sentiment.get('trend', 'N/A')}")
    print(f"  Positive:           {sentiment.get('positive_count', '?')}")
    print(f"  Negative:           {sentiment.get('negative_count', '?')}")
    print(f"  Market Position:    {analysis_state.get('competitor_analysis', {}).get('market_position', 'N/A')}")
    print(f"  Insights:           {len(analysis_state.get('insights', []))}")
    print(f"  Recommendations:    {len(analysis_state.get('recommendations', []))}")
    print(f"  Review Responses:   {len(responses)}")
    print(f"  Report HTML:        {len(report_html):,} chars")
    print(f"  Total Claude Calls: ~14")
    print(f"  Total Time:         {elapsed:.1f}s")

    errors = analysis_state.get("errors", [])
    if errors:
        print(f"\n  Errors: {errors}")

    all_pass = analysis_ok and report_ok and responses_ok
    print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")

    print(f"\n  Preview reports:")
    print(f"    {report_path}")
    print(f"    {combined_path}")

    return 0 if all_pass else 1


def _build_combined_report(report_html: str, responses: list[dict]) -> str:
    """Append a Review Responses section to the report HTML."""
    rows = []
    for r in responses:
        stars = int(r["rating"])
        star_str = "&#9733;" * stars + "&#9734;" * (5 - stars)
        rows.append(f"""
        <div style="background: #f8f9fa; border-radius: 10px; padding: 18px; margin-bottom: 12px;">
          <p style="margin: 0 0 6px 0;">
            <span style="font-size: 14px; letter-spacing: 1px;">{star_str}</span>
            <strong style="margin-left: 6px;">{r['reviewer_name']}</strong>
            <span style="color: #888; font-size: 12px; margin-left: 8px;">{r['strategy']}</span>
          </p>
          <p style="margin: 0 0 10px 0; color: #444; font-size: 14px; line-height: 1.5;">&ldquo;{r['review_text'][:200]}...&rdquo;</p>
          <div style="background: #eef2ff; border-left: 3px solid #667eea; border-radius: 0 6px 6px 0; padding: 12px;">
            <p style="margin: 0 0 4px 0; font-size: 11px; color: #888; text-transform: uppercase;">Suggested Response ({r['tone']})</p>
            <p style="margin: 0; color: #333; font-size: 13px; line-height: 1.5;">{r['ai_response']}</p>
          </div>
        </div>""")

    responses_section = f"""
    <div style="padding: 30px; border-top: 1px solid #eee;">
      <h2 style="font-size: 18px; font-weight: 700; color: #1a1a2e; margin-bottom: 20px;
                 padding-bottom: 10px; border-bottom: 3px solid #667eea; display: inline-block;">
        AI-Generated Review Responses
      </h2>
      {''.join(rows)}
    </div>"""

    # Insert before the closing footer div
    insertion_point = report_html.rfind("<!-- Footer -->")
    if insertion_point == -1:
        insertion_point = report_html.rfind('<div class="footer">')
    if insertion_point == -1:
        return report_html + responses_section

    return report_html[:insertion_point] + responses_section + "\n        " + report_html[insertion_point:]


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
