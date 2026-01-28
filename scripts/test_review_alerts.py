#!/usr/bin/env python3
"""
Test Script for Review Alert System.

Tests single-review alerts and weekly digest email rendering, including
AI response generation. Outputs HTML files to /tmp for visual inspection.

Test Cases:
1. 5-star review alert for a dog groomer
2. 2-star negative review alert (verify empathy strategy)
3. Weekly digest with 5 sample reviews
4. Verify HTML output files are written for inspection

Usage:
    python scripts/test_review_alerts.py
    python scripts/test_review_alerts.py --verbose
    python scripts/test_review_alerts.py --case alert_positive
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, ".")


# =============================================================================
# Test Data
# =============================================================================

BUSINESS = {
    "business_name": "Pawfect Grooming Leeds",
    "business_email": "owner@pawfect.com",
    "business_type": "dog grooming salon",
    "google_place_id": "ChIJexampleGroomer123",
}

POSITIVE_REVIEW = {
    "reviewer_name": "Emma",
    "rating": 5.0,
    "review_text": (
        "Absolutely love Pawfect Grooming! My cockapoo Bella always comes out "
        "looking gorgeous. The staff are so gentle with her and she actually "
        "enjoys going now. Highly recommend!"
    ),
    "review_date": "25 Jan 2026",
}

NEGATIVE_REVIEW = {
    "reviewer_name": "James",
    "rating": 2.0,
    "review_text": (
        "Booked a 10am appointment but wasn't seen until 10:45. Then the groom "
        "took over 2 hours when I was told 90 minutes. The actual grooming was "
        "okay but the wait and lack of communication was really frustrating."
    ),
    "review_date": "23 Jan 2026",
}

DIGEST_REVIEWS = [
    POSITIVE_REVIEW,
    NEGATIVE_REVIEW,
    {
        "reviewer_name": "Sophie",
        "rating": 4.0,
        "review_text": (
            "Really friendly team and my spaniel looked great afterwards. "
            "Only minor issue was the price — a bit more than I expected for "
            "a basic wash and trim. Would still recommend though."
        ),
        "review_date": "22 Jan 2026",
    },
    {
        "reviewer_name": "Mike",
        "rating": 5.0,
        "review_text": (
            "First time bringing our rescue greyhound and the staff were amazing. "
            "So patient and gentle with him. The shop was spotless too. "
            "Will definitely be back!"
        ),
        "review_date": "21 Jan 2026",
    },
    {
        "reviewer_name": "Aisha",
        "rating": 3.0,
        "review_text": (
            "The grooming itself was fine but I had to wait 20 minutes past my "
            "appointment time with no explanation. Staff were friendly once I was "
            "seen though. Clean premises."
        ),
        "review_date": "20 Jan 2026",
    },
]


# =============================================================================
# Display Helpers
# =============================================================================

def print_header(text: str, char: str = "=") -> None:
    line = char * 70
    print(f"\n{line}")
    print(f" {text}")
    print(f"{line}\n")


def print_result(label: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label}")
    if detail:
        print(f"         {detail}")


def write_html(name: str, html: str) -> Path:
    """Write HTML to a temp file and return the path."""
    path = Path(f"/tmp/localpulse_{name}.html")
    path.write_text(html, encoding="utf-8")
    return path


# =============================================================================
# Test Cases
# =============================================================================

async def test_alert_positive(verbose: bool = False) -> bool:
    """Test 1: 5-star review alert for dog groomer."""
    from src.services.review_alerts import (
        ReviewAlertService, ReviewAlertInput, ReviewData,
    )

    print("  Generating AI response and rendering email...")
    service = ReviewAlertService()
    alert = ReviewAlertInput(
        **BUSINESS,
        review=ReviewData(**POSITIVE_REVIEW),
    )
    subject, html, plain = await service.render_review_alert(alert)

    checks = []

    has_subject = "Emma" in subject and "⭐" in subject
    checks.append(has_subject)

    has_stars = "&#9733;" in html
    checks.append(has_stars)

    has_name = "Emma" in html
    checks.append(has_name)

    has_review = "cockapoo" in html
    checks.append(has_review)

    has_ai = "Suggested Response" in html
    checks.append(has_ai)

    has_google_link = "ChIJexampleGroomer123" in html
    checks.append(has_google_link)

    has_plain = "Emma" in plain and "Suggested response:" in plain
    checks.append(has_plain)

    passed = all(checks)

    path = write_html("alert_positive", html)
    print_result(
        "5-star review alert",
        passed,
        f"subject={has_subject}, stars={has_stars}, ai={has_ai}, link={has_google_link}",
    )
    print(f"         HTML: {path}")

    if verbose:
        print(f"\n  Subject: {subject}")
        print(f"\n  Plain text:\n  {plain[:300]}...")

    return passed


async def test_alert_negative(verbose: bool = False) -> bool:
    """Test 2: 2-star negative review alert — verify empathy strategy."""
    from src.services.review_alerts import (
        ReviewAlertService, ReviewAlertInput, ReviewData,
    )

    print("  Generating AI response and rendering email...")
    service = ReviewAlertService()
    alert = ReviewAlertInput(
        **BUSINESS,
        review=ReviewData(**NEGATIVE_REVIEW),
    )
    subject, html, plain = await service.render_review_alert(alert)

    checks = []

    # Subject should have 2 stars
    star_count = subject.count("⭐")
    has_two_stars = star_count == 2
    checks.append(has_two_stars)

    # Strategy should be empathy-related
    has_empathy = "Empathy" in html
    checks.append(has_empathy)

    # AI response should exist
    has_ai = len(plain) > 100
    checks.append(has_ai)

    passed = all(checks)

    path = write_html("alert_negative", html)
    print_result(
        "2-star review alert (empathy strategy)",
        passed,
        f"stars_in_subject={star_count}, empathy={has_empathy}, has_ai={has_ai}",
    )
    print(f"         HTML: {path}")

    if verbose:
        print(f"\n  Subject: {subject}")
        print(f"\n  Plain text:\n  {plain[:400]}...")

    return passed


async def test_weekly_digest(verbose: bool = False) -> bool:
    """Test 3: Weekly digest with 5 sample reviews."""
    from src.services.review_alerts import (
        ReviewAlertService, WeeklyDigestInput, ReviewData,
    )

    print("  Generating AI responses for 5 reviews...")
    service = ReviewAlertService()
    digest = WeeklyDigestInput(
        **BUSINESS,
        reviews=[ReviewData(**r) for r in DIGEST_REVIEWS],
        period_start="20 Jan 2026",
        period_end="26 Jan 2026",
        prev_avg_rating=4.0,
    )
    subject, html, plain = await service.render_weekly_digest(digest)

    checks = []

    # Subject includes count and avg
    has_count = "5 reviews" in subject
    checks.append(has_count)

    # HTML has stats section
    has_stats = "Avg Rating" in html
    checks.append(has_stats)

    # HTML has all 5 reviewer names
    all_names = all(
        r["reviewer_name"] in html for r in DIGEST_REVIEWS
    )
    checks.append(all_names)

    # HTML has rating distribution bars
    has_distribution = "Rating Breakdown" in html
    checks.append(has_distribution)

    # HTML has insights section
    has_insights = "Quick Insights" in html
    checks.append(has_insights)

    # Plain text has all reviews
    plain_has_all = all(
        r["reviewer_name"] in plain for r in DIGEST_REVIEWS
    )
    checks.append(plain_has_all)

    passed = all(checks)

    path = write_html("weekly_digest", html)
    print_result(
        "Weekly digest with 5 reviews",
        passed,
        f"count={has_count}, stats={has_stats}, names={all_names}, "
        f"dist={has_distribution}, insights={has_insights}",
    )
    print(f"         HTML: {path}")

    if verbose:
        print(f"\n  Subject: {subject}")
        print(f"\n  Plain text (first 500 chars):\n  {plain[:500]}...")

    return passed


async def test_html_output(verbose: bool = False) -> bool:
    """Test 4: Verify HTML files were written and are valid."""
    files = [
        "localpulse_alert_positive.html",
        "localpulse_alert_negative.html",
        "localpulse_weekly_digest.html",
    ]
    checks = []
    for name in files:
        path = Path(f"/tmp/{name}")
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        ok = exists and size > 1000  # sanity: at least 1KB of HTML
        checks.append(ok)
        print_result(
            f"{name}",
            ok,
            f"exists={exists}, size={size:,} bytes",
        )

    passed = all(checks)
    if passed:
        print(f"\n  Open in browser to inspect:")
        for name in files:
            print(f"    file:///tmp/{name}")
    return passed


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="Test the Review Alert System"
    )
    parser.add_argument(
        "--case", "-c",
        choices=["alert_positive", "alert_negative", "digest", "html", "all"],
        default="all",
        help="Which test case to run",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    print_header("LocalPulse Review Alert System Test")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    test_map = {
        "alert_positive": ("5-Star Review Alert", test_alert_positive),
        "alert_negative": ("2-Star Review Alert (Empathy)", test_alert_negative),
        "digest": ("Weekly Digest — 5 Reviews", test_weekly_digest),
        "html": ("HTML Output Verification", test_html_output),
    }

    cases = list(test_map.keys()) if args.case == "all" else [args.case]
    passed = 0
    failed = 0

    for key in cases:
        label, fn = test_map[key]
        print_header(label, char="-")
        ok = await fn(args.verbose)
        if ok:
            passed += 1
        else:
            failed += 1

    print_header("Results")
    print(f"  Passed: {passed}/{passed + failed}")
    if failed:
        print(f"  Failed: {failed}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
