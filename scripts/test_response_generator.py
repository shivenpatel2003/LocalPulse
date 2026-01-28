#!/usr/bin/env python3
"""
Test Script for Review Response Generator.

Tests the AI-powered review response generation with 3 review scenarios:
1. 5-star positive review for a dog groomer
2. 2-star negative review complaining about wait time
3. 3-star mixed review for a restaurant

Usage:
    python scripts/test_response_generator.py
    python scripts/test_response_generator.py --verbose
    python scripts/test_response_generator.py --case positive
"""

import argparse
import asyncio
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, ".")


# =============================================================================
# Test Cases
# =============================================================================

TEST_REVIEWS = {
    "positive": {
        "label": "5-Star Positive — Dog Groomer",
        "input": {
            "reviewer_name": "Emma",
            "rating": 5.0,
            "review_text": (
                "Absolutely love Pawfect Grooming! My cockapoo Bella always comes out "
                "looking gorgeous. The staff are so gentle with her and she actually "
                "enjoys going now. The puppy first groom package was brilliant — they "
                "took their time and made her feel safe. Highly recommend!"
            ),
            "business_name": "Pawfect Grooming Leeds",
            "business_type": "dog grooming salon",
        },
    },
    "negative": {
        "label": "2-Star Negative — Wait Time Complaint",
        "input": {
            "reviewer_name": "James",
            "rating": 2.0,
            "review_text": (
                "Booked a 10am appointment for my labrador but wasn't seen until "
                "10:45. Then the groom took over 2 hours when I was told it would be "
                "90 minutes. The actual grooming was okay but the wait and lack of "
                "communication was really frustrating. Won't be rushing back."
            ),
            "business_name": "Pawfect Grooming Leeds",
            "business_type": "dog grooming salon",
        },
    },
    "mixed": {
        "label": "3-Star Mixed — Restaurant",
        "input": {
            "reviewer_name": "Priya",
            "rating": 3.0,
            "review_text": (
                "The food was genuinely excellent — the lamb shank was the best I've "
                "had in Manchester. However, the service was painfully slow. We waited "
                "40 minutes for starters and our drinks order was forgotten. Nice "
                "atmosphere though and good value for the portion sizes."
            ),
            "business_name": "The Oak Table",
            "business_type": "restaurant",
        },
    },
}


# =============================================================================
# Display Helpers
# =============================================================================

def print_header(text: str, char: str = "=") -> None:
    line = char * 70
    print(f"\n{line}")
    print(f" {text}")
    print(f"{line}\n")


def print_subheader(text: str) -> None:
    print(f"\n--- {text} ---\n")


def print_review_input(label: str, data: dict) -> None:
    print(f"  Reviewer:  {data['reviewer_name']}")
    print(f"  Rating:    {'★' * int(data['rating'])}{'☆' * (5 - int(data['rating']))}  ({data['rating']}/5)")
    print(f"  Business:  {data['business_name']} ({data['business_type']})")
    print(f"  Review:    {data['review_text'][:120]}...")


def print_response(response, verbose: bool = False) -> None:
    print(f"\n  Response:  {response.response_text}")
    print(f"  Tone:      {response.tone_used.value}")
    print(f"  Strategy:  {response.strategy.value}")
    print(f"  Words:     {response.word_count}")
    if verbose:
        sentences = [s.strip() for s in response.response_text.split(".") if s.strip()]
        print(f"  Sentences: ~{len(sentences)}")


# =============================================================================
# Test Runner
# =============================================================================

async def run_test(case_key: str, verbose: bool = False) -> bool:
    """Run a single test case. Returns True on success."""
    from src.services.response_generator import ReviewResponseGenerator, ReviewInput

    case = TEST_REVIEWS[case_key]
    print_header(case["label"], char="-")
    print_review_input(case["label"], case["input"])

    generator = ReviewResponseGenerator()
    review = ReviewInput(**case["input"])

    print("\n  Generating response...")
    try:
        response = await generator.generate_response(review)
        print_response(response, verbose)
        return True
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    parser = argparse.ArgumentParser(
        description="Test the Review Response Generator"
    )
    parser.add_argument(
        "--case", "-c",
        choices=["positive", "negative", "mixed", "all"],
        default="all",
        help="Which test case to run",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    print_header("LocalPulse Review Response Generator Test")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    cases = list(TEST_REVIEWS.keys()) if args.case == "all" else [args.case]
    passed = 0
    failed = 0

    for key in cases:
        ok = await run_test(key, args.verbose)
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
