#!/usr/bin/env python3
"""
Test Script for Review Request System.

Tests review request generation for email and SMS channels, validates
SMS character limits, and verifies Google review URL construction.

Test Cases:
1. Generate email request for dog groomer customer
2. Generate SMS request for restaurant customer
3. Verify SMS is under 160 characters
4. Verify Google review URL is correctly formatted

Usage:
    python scripts/test_review_requests.py
    python scripts/test_review_requests.py --verbose
    python scripts/test_review_requests.py --case email
"""

import argparse
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, ".")


# =============================================================================
# Test Data
# =============================================================================

GROOMER_INPUT = {
    "customer_name": "Emma",
    "business_name": "Pawfect Grooming Leeds",
    "business_type": "dog grooming salon",
    "google_place_id": "ChIJexampleGroomer123",
    "customer_email": "emma@example.com",
}

RESTAURANT_INPUT = {
    "customer_name": "Priya",
    "business_name": "The Oak Table",
    "business_type": "restaurant",
    "google_place_id": "ChIJexampleRestaurant456",
    "customer_phone": "+447700900123",
}

ACCOUNTANT_INPUT = {
    "customer_name": "James",
    "business_name": "Clarke & Partners",
    "business_type": "accountant",
    "google_place_id": "ChIJexampleAccountant789",
    "customer_email": "james@example.com",
}


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


# =============================================================================
# Test Cases
# =============================================================================

def test_email_groomer(verbose: bool = False) -> bool:
    """Test 1: Generate email request for dog groomer customer."""
    from src.services.review_requests import ReviewRequestGenerator, ReviewRequestInput

    gen = ReviewRequestGenerator()
    req = ReviewRequestInput(**GROOMER_INPUT)
    result = gen.generate_email_request(req)

    checks = []

    # Has subject
    has_subject = result.subject is not None and len(result.subject) > 0
    checks.append(has_subject)

    # Body is HTML
    is_html = "<html" in result.body.lower() and "</html>" in result.body.lower()
    checks.append(is_html)

    # Contains customer name
    has_name = "Emma" in result.body
    checks.append(has_name)

    # Contains business name
    has_biz = "Pawfect Grooming Leeds" in result.body
    checks.append(has_biz)

    # Contains review URL
    has_url = "ChIJexampleGroomer123" in result.review_url
    checks.append(has_url)

    # Channel is email
    is_email = result.channel.value == "email"
    checks.append(is_email)

    passed = all(checks)
    print_result(
        "Email request for dog groomer",
        passed,
        f"subject='{result.subject}', html={is_html}, name={has_name}, url={has_url}",
    )

    if verbose:
        print(f"\n  --- Email Subject ---\n  {result.subject}")
        print(f"\n  --- Review URL ---\n  {result.review_url}")
        print(f"\n  --- Email Body (first 500 chars) ---\n  {result.body[:500]}...")

    return passed


def test_sms_restaurant(verbose: bool = False) -> bool:
    """Test 2: Generate SMS request for restaurant customer."""
    from src.services.review_requests import ReviewRequestGenerator, ReviewRequestInput

    gen = ReviewRequestGenerator()
    req = ReviewRequestInput(**RESTAURANT_INPUT)
    result = gen.generate_sms_request(req)

    checks = []

    # No subject for SMS
    no_subject = result.subject is None
    checks.append(no_subject)

    # Contains customer name
    has_name = "Priya" in result.body
    checks.append(has_name)

    # Contains business name
    has_biz = "The Oak Table" in result.body
    checks.append(has_biz)

    # Contains review URL
    has_url = result.review_url in result.body
    checks.append(has_url)

    # Channel is SMS
    is_sms = result.channel.value == "sms"
    checks.append(is_sms)

    passed = all(checks)
    print_result(
        "SMS request for restaurant",
        passed,
        f"no_subject={no_subject}, name={has_name}, biz={has_biz}, url_in_body={has_url}",
    )

    if verbose:
        print(f"\n  --- SMS Body ---\n  {result.body}")
        print(f"  --- Length: {len(result.body)} chars ---")

    return passed


def test_sms_length(verbose: bool = False) -> bool:
    """Test 3: Verify SMS is under 160 characters."""
    from src.services.review_requests import ReviewRequestGenerator, ReviewRequestInput, SMS_MAX_LENGTH

    gen = ReviewRequestGenerator()

    # Test with all three inputs to be thorough
    inputs = [
        ("groomer", GROOMER_INPUT),
        ("restaurant", RESTAURANT_INPUT),
        ("accountant", ACCOUNTANT_INPUT),
    ]
    all_ok = True
    details = []

    for label, data in inputs:
        req = ReviewRequestInput(**data)
        result = gen.generate_sms_request(req)
        length = len(result.body)
        ok = length <= SMS_MAX_LENGTH
        details.append(f"{label}={length}ch")
        if not ok:
            all_ok = False

    print_result(
        f"SMS under {SMS_MAX_LENGTH} chars",
        all_ok,
        f"lengths: {', '.join(details)}",
    )

    if verbose:
        for label, data in inputs:
            req = ReviewRequestInput(**data)
            result = gen.generate_sms_request(req)
            print(f"\n  --- {label} SMS ({len(result.body)} chars) ---\n  {result.body}")

    return all_ok


def test_google_review_url(verbose: bool = False) -> bool:
    """Test 4: Verify Google review URL is correctly formatted."""
    from src.services.review_requests import build_google_review_url

    test_place_id = "ChIJN1t_tDeuEmsRUsoyG83frY4"
    expected = f"https://search.google.com/local/writereview?placeid={test_place_id}"
    result = build_google_review_url(test_place_id)

    passed = result == expected
    print_result(
        "Google review URL format",
        passed,
        f"url={result}",
    )

    if verbose:
        print(f"\n  Expected: {expected}")
        print(f"  Got:      {result}")
        print(f"  Match:    {passed}")

    return passed


# =============================================================================
# Bonus: Tone Matching
# =============================================================================

def test_tone_matching(verbose: bool = False) -> bool:
    """Bonus: Verify tone varies by business type."""
    from src.services.review_requests import ReviewRequestGenerator, ReviewRequestInput

    gen = ReviewRequestGenerator()

    groomer_req = ReviewRequestInput(**GROOMER_INPUT)
    accountant_req = ReviewRequestInput(**ACCOUNTANT_INPUT)

    groomer_email = gen.generate_email_request(groomer_req)
    accountant_email = gen.generate_email_request(accountant_req)

    # Groomer should get "Hi", accountant should get "Dear"
    groomer_has_hi = "Hi" in groomer_email.body.split("</p>")[0]
    accountant_has_dear = "Dear" in accountant_email.body.split("</p>")[0]

    passed = groomer_has_hi and accountant_has_dear
    print_result(
        "Tone varies by business type",
        passed,
        f"groomer_greeting='Hi'={groomer_has_hi}, accountant_greeting='Dear'={accountant_has_dear}",
    )

    if verbose:
        # Show the header colours differ
        groomer_colour = "#4CAF50" in groomer_email.body
        accountant_colour = "#2C3E50" in accountant_email.body
        print(f"  Groomer header colour (green):  {groomer_colour}")
        print(f"  Accountant header colour (dark): {accountant_colour}")

    return passed


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Test the Review Request System"
    )
    parser.add_argument(
        "--case", "-c",
        choices=["email", "sms", "length", "url", "tone", "all"],
        default="all",
        help="Which test case to run",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    print_header("LocalPulse Review Request System Test")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    test_map = {
        "email": ("Email Request — Dog Groomer", test_email_groomer),
        "sms": ("SMS Request — Restaurant", test_sms_restaurant),
        "length": ("SMS Length Validation", test_sms_length),
        "url": ("Google Review URL Format", test_google_review_url),
        "tone": ("Tone Matching by Business Type", test_tone_matching),
    }

    cases = list(test_map.keys()) if args.case == "all" else [args.case]
    passed = 0
    failed = 0

    for key in cases:
        label, fn = test_map[key]
        print_header(label, char="-")
        ok = fn(args.verbose)
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
    sys.exit(main())
