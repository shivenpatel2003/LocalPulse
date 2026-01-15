#!/usr/bin/env python3
"""End-to-end API test script for LocalPulse.

This script tests the API endpoints without requiring the full Supabase setup.
It prints the curl commands for each operation and shows expected responses.

Usage:
    python scripts/test_api_e2e.py
"""

import json
from datetime import datetime

# =============================================================================
# Test Configuration
# =============================================================================

BASE_URL = "http://127.0.0.1:8000"
API_V1 = f"{BASE_URL}/api/v1"

TEST_CLIENT = {
    "business_name": "Circolo Popolare Manchester",
    "location": "Manchester, UK",
    "email": "test@example.com",
    "frequency": "weekly",
    "schedule_day": "monday",
    "schedule_hour": 9
}


# =============================================================================
# Print Curl Commands
# =============================================================================

def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def print_curl_commands() -> None:
    """Print all curl commands for testing the API."""

    print_section("LocalPulse API - End-to-End Test Commands")
    print(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}")

    # -------------------------------------------------------------------------
    # 1. Health Check
    # -------------------------------------------------------------------------
    print_section("1. Health Check")
    print("\n# Check if server is running:")
    print(f'curl -s {BASE_URL}/health/live')
    print("\n# Expected response:")
    print('{"status":"alive","timestamp":"2024-01-15T12:00:00.000000+00:00"}')

    print("\n# Full health check (all services):")
    print(f'curl -s {BASE_URL}/health | python -m json.tool')

    # -------------------------------------------------------------------------
    # 2. Add Test Client
    # -------------------------------------------------------------------------
    print_section("2. Add Test Client")

    client_json = json.dumps(TEST_CLIENT, indent=2)
    client_json_oneline = json.dumps(TEST_CLIENT)

    print("\n# Create a new client:")
    print(f'''curl -X POST {API_V1}/clients \\
  -H "Content-Type: application/json" \\
  -d '{client_json_oneline}' ''')

    print("\n# Request body:")
    print(client_json)

    print("\n# Expected response (201 Created):")
    print('''{
  "id": "uuid-here",
  "client_id": "uuid-here",
  "business_name": "Circolo Popolare Manchester",
  "location": "Manchester, UK",
  "email": "test@example.com",
  "frequency": "weekly",
  "schedule_day": "monday",
  "schedule_hour": 9,
  "is_active": true,
  "last_run": null,
  "next_run": "2024-01-22T09:00:00+00:00",
  "created_at": "2024-01-15T12:00:00+00:00"
}''')

    # -------------------------------------------------------------------------
    # 3. List All Clients
    # -------------------------------------------------------------------------
    print_section("3. List All Clients")

    print("\n# Get all clients:")
    print(f'curl -s {API_V1}/clients | python -m json.tool')

    print("\n# Filter by active status:")
    print(f'curl -s "{API_V1}/clients?is_active=true" | python -m json.tool')

    # -------------------------------------------------------------------------
    # 4. Get Client Details
    # -------------------------------------------------------------------------
    print_section("4. Get Client Details")

    print("\n# Get specific client (replace CLIENT_ID with actual UUID):")
    print(f'curl -s {API_V1}/clients/CLIENT_ID | python -m json.tool')

    print("\n# Example with variable:")
    print(f'''CLIENT_ID="your-client-uuid-here"
curl -s {API_V1}/clients/$CLIENT_ID | python -m json.tool''')

    # -------------------------------------------------------------------------
    # 5. Trigger Immediate Report Run
    # -------------------------------------------------------------------------
    print_section("5. Trigger Immediate Report Run")

    print("\n# Trigger report generation (replace CLIENT_ID):")
    print(f'''curl -X POST {API_V1}/reports/CLIENT_ID/run \\
  -H "Content-Type: application/json" \\
  -d '{{"send_email": false}}' ''')

    print("\n# Expected response:")
    print('''{
  "success": true,
  "business_name": "Circolo Popolare Manchester",
  "phase_completed": "complete",
  "duration_seconds": 45.2,
  "collection_summary": {
    "status": "completed",
    "reviews_collected": 5,
    "competitors_found": 19
  },
  "analysis_summary": {
    "status": "completed",
    "sentiment_score": 0.84,
    "insights_count": 5,
    "recommendations_count": 5
  },
  "report_summary": {
    "status": "completed",
    "html_generated": true
  },
  "errors": []
}''')

    # -------------------------------------------------------------------------
    # 6. Get Latest Report
    # -------------------------------------------------------------------------
    print_section("6. Get Latest Report")

    print("\n# Get latest report for client:")
    print(f'curl -s {API_V1}/reports/CLIENT_ID | python -m json.tool')

    print("\n# Get report history:")
    print(f'curl -s "{API_V1}/reports/CLIENT_ID/history?limit=5" | python -m json.tool')

    # -------------------------------------------------------------------------
    # 7. Schedule Management
    # -------------------------------------------------------------------------
    print_section("7. Schedule Management")

    print("\n# List all schedules:")
    print(f'curl -s {API_V1}/schedules | python -m json.tool')

    print("\n# Pause a client's schedule:")
    print(f'curl -X PUT {API_V1}/schedules/CLIENT_ID/pause')

    print("\n# Resume a client's schedule:")
    print(f'curl -X PUT {API_V1}/schedules/CLIENT_ID/resume')

    # -------------------------------------------------------------------------
    # 8. Update Client
    # -------------------------------------------------------------------------
    print_section("8. Update Client")

    print("\n# Update client settings:")
    print(f'''curl -X PUT {API_V1}/clients/CLIENT_ID \\
  -H "Content-Type: application/json" \\
  -d '{{"frequency": "daily", "schedule_hour": 8}}' ''')

    # -------------------------------------------------------------------------
    # 9. Delete Client
    # -------------------------------------------------------------------------
    print_section("9. Delete Client")

    print("\n# Delete a client (careful!):")
    print(f'curl -X DELETE {API_V1}/clients/CLIENT_ID')
    print("\n# Returns 204 No Content on success")

    # -------------------------------------------------------------------------
    # Full Test Script
    # -------------------------------------------------------------------------
    print_section("Complete Test Script (Bash)")

    print('''
#!/bin/bash
# Full end-to-end test script for LocalPulse API

BASE_URL="http://127.0.0.1:8000"
API_V1="$BASE_URL/api/v1"

echo "=== 1. Health Check ==="
curl -s $BASE_URL/health/live
echo ""

echo "=== 2. Create Test Client ==="
RESPONSE=$(curl -s -X POST $API_V1/clients \\
  -H "Content-Type: application/json" \\
  -d '{"business_name":"Circolo Popolare Manchester","location":"Manchester, UK","email":"test@example.com","frequency":"weekly","schedule_day":"monday","schedule_hour":9}')
echo $RESPONSE | python -m json.tool

# Extract client_id from response (requires jq)
# CLIENT_ID=$(echo $RESPONSE | jq -r '.client_id')
# Or manually set it:
# CLIENT_ID="paste-uuid-here"

echo "=== 3. List Clients ==="
curl -s $API_V1/clients | python -m json.tool

echo "=== 4. List Schedules ==="
curl -s $API_V1/schedules | python -m json.tool

# Uncomment below after setting CLIENT_ID:
# echo "=== 5. Trigger Report Run ==="
# curl -s -X POST $API_V1/reports/$CLIENT_ID/run \\
#   -H "Content-Type: application/json" \\
#   -d '{"send_email":false}' | python -m json.tool

# echo "=== 6. Get Report ==="
# curl -s $API_V1/reports/$CLIENT_ID | python -m json.tool

echo "=== Test Complete ==="
''')

    # -------------------------------------------------------------------------
    # Python Requests Example
    # -------------------------------------------------------------------------
    print_section("Python Requests Example")

    print('''
import httpx
import asyncio

BASE_URL = "http://127.0.0.1:8000"
API_V1 = f"{BASE_URL}/api/v1"

async def test_api():
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Health check
        print("1. Health Check")
        r = await client.get(f"{BASE_URL}/health/live")
        print(f"   Status: {r.status_code}")
        print(f"   Response: {r.json()}")

        # 2. Create client
        print("\\n2. Create Client")
        r = await client.post(f"{API_V1}/clients", json={
            "business_name": "Circolo Popolare Manchester",
            "location": "Manchester, UK",
            "email": "test@example.com",
            "frequency": "weekly",
            "schedule_day": "monday",
            "schedule_hour": 9
        })
        print(f"   Status: {r.status_code}")
        client_data = r.json()
        print(f"   Client ID: {client_data.get('client_id')}")
        client_id = client_data.get('client_id')

        # 3. List clients
        print("\\n3. List Clients")
        r = await client.get(f"{API_V1}/clients")
        print(f"   Status: {r.status_code}")
        print(f"   Total: {r.json().get('total')}")

        # 4. Trigger report (this takes time!)
        print("\\n4. Trigger Report Run")
        print("   (This may take 30-60 seconds...)")
        r = await client.post(
            f"{API_V1}/reports/{client_id}/run",
            json={"send_email": False}
        )
        print(f"   Status: {r.status_code}")
        result = r.json()
        print(f"   Success: {result.get('success')}")
        print(f"   Phase: {result.get('phase_completed')}")
        print(f"   Duration: {result.get('duration_seconds')}s")

        # 5. Get report
        print("\\n5. Get Latest Report")
        r = await client.get(f"{API_V1}/reports/{client_id}")
        print(f"   Status: {r.status_code}")

        # 6. Clean up - delete client
        print("\\n6. Delete Client")
        r = await client.delete(f"{API_V1}/clients/{client_id}")
        print(f"   Status: {r.status_code}")

        print("\\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_api())
''')

    print("\n" + "=" * 70)
    print(" End of Test Commands")
    print("=" * 70)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print_curl_commands()
