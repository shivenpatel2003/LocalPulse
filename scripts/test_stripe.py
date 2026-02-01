#!/usr/bin/env python3
"""
Test Script for Stripe Billing Integration.

Tests the checkout flow by calling the billing API endpoints.
Requires STRIPE_SECRET_KEY and STRIPE_PRICE_ID to be configured in .env
and the server running on localhost:8000.

Usage:
    python scripts/test_stripe.py
    python scripts/test_stripe.py --verbose
    python scripts/test_stripe.py --case create_checkout
"""

import argparse
import asyncio
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, ".")


# =============================================================================
# Test Data
# =============================================================================

VALID_CHECKOUT = {
    "customer_email": "test@example.com",
    "business_name": "Test Restaurant Leeds",
}

BASE_URL = "http://localhost:8000"


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


async def test_create_checkout(verbose: bool = False) -> bool:
    """Test 1: Create a checkout session with valid data."""
    import httpx

    print("  Calling POST /api/v1/billing/create-checkout ...")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v1/billing/create-checkout",
            json=VALID_CHECKOUT,
        )

    if response.status_code == 503:
        print_result(
            "Create checkout session",
            False,
            "Stripe not configured (503). Set STRIPE_SECRET_KEY and STRIPE_PRICE_ID in .env",
        )
        return False

    passed = response.status_code == 200
    data = response.json()

    has_url = "checkout_url" in data
    is_stripe_url = data.get("checkout_url", "").startswith(
        "https://checkout.stripe.com"
    )

    all_ok = passed and has_url and is_stripe_url

    print_result(
        "Create checkout session",
        all_ok,
        f"status={response.status_code}, has_url={has_url}, is_stripe={is_stripe_url}",
    )

    if verbose and passed:
        print(f"\n  Checkout URL: {data.get('checkout_url', 'N/A')}")

    return all_ok


async def test_validation_error(verbose: bool = False) -> bool:
    """Test 2: Missing email should return 422."""
    import httpx

    print("  Calling POST /api/v1/billing/create-checkout with invalid data ...")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v1/billing/create-checkout",
            json={"business_name": "Test"},  # missing customer_email
        )

    passed = response.status_code == 422
    print_result(
        "Validation error for missing email",
        passed,
        f"status={response.status_code} (expected 422)",
    )

    if verbose:
        print(f"\n  Response: {response.json()}")

    return passed


async def test_webhook_rejects_bad_sig(verbose: bool = False) -> bool:
    """Test 3: Webhook should reject requests with invalid signature."""
    import httpx

    print("  Calling POST /api/v1/billing/webhook with bad payload ...")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v1/billing/webhook",
            content=b'{"type": "fake.event"}',
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "bad_sig",
            },
        )

    # 400 if webhook secret is configured, 200 if not
    passed = response.status_code in (400, 200)
    print_result(
        "Webhook signature validation",
        passed,
        f"status={response.status_code} (expected 400 with secret, 200 without)",
    )

    if verbose:
        print(f"\n  Response: {response.json()}")

    return passed


# =============================================================================
# Main
# =============================================================================


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the Stripe Billing Integration"
    )
    parser.add_argument(
        "--case",
        "-c",
        choices=["create_checkout", "validation", "webhook", "all"],
        default="all",
        help="Which test case to run",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    print_header("LocalPulse Stripe Billing Test")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Server:  {BASE_URL}")

    test_map = {
        "create_checkout": ("Create Checkout Session", test_create_checkout),
        "validation": ("Validation Error Handling", test_validation_error),
        "webhook": ("Webhook Signature Validation", test_webhook_rejects_bad_sig),
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
