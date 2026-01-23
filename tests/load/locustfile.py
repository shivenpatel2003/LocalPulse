"""Load tests for LocalPulse API using Locust.

Run with:
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Or headless:
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
           --headless -u 50 -r 10 -t 60s

Configuration:
    - Users: 50-100 concurrent users for normal load
    - Spawn rate: 10 users/second
    - Duration: 60 seconds minimum for meaningful results

Expected baselines:
    - Health check: <50ms p95
    - Pipeline trigger: <500ms p95
    - Report generation: <5s p95
"""

import random

from locust import HttpUser, between, events, task


class LocalPulseUser(HttpUser):
    """
    Simulates a typical LocalPulse user interacting with the API.

    User behavior:
    - Frequently checks health endpoint (monitoring)
    - Occasionally triggers data collection
    - Sometimes requests analysis
    - Rarely generates full reports
    """

    # Wait 1-3 seconds between tasks (simulates think time)
    wait_time = between(1, 3)

    def on_start(self):
        """Called when user starts - can be used for auth."""
        # If API key auth is enabled, set header
        self.api_key = "test-api-key"  # Would come from env in real tests
        self.headers = {}
        # Uncomment when API key auth is enabled:
        # self.headers = {"X-API-Key": self.api_key}

    @task(10)
    def health_check(self):
        """
        Health check endpoint - most frequent operation.

        Weight: 10 (called 10x more than other tasks)
        Expected: <50ms response time
        """
        with self.client.get(
            "/health",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    def get_metrics(self):
        """
        Prometheus metrics endpoint.

        Weight: 5
        Expected: <100ms response time
        """
        with self.client.get(
            "/metrics",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics failed: {response.status_code}")

    @task(3)
    def list_businesses(self):
        """
        List businesses endpoint.

        Weight: 3
        Expected: <200ms response time
        """
        # Sample location for testing
        location = random.choice([
            "Austin, TX",
            "San Francisco, CA",
            "New York, NY",
        ])

        with self.client.get(
            f"/api/v1/businesses?location={location}&limit=10",
            headers=self.headers,
            catch_response=True,
            name="/api/v1/businesses"
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(f"List businesses failed: {response.status_code}")

    @task(2)
    def trigger_collection(self):
        """
        Trigger data collection for a business.

        Weight: 2 (less frequent - this is an expensive operation)
        Expected: <500ms to accept, async processing
        """
        payload = {
            "business_id": f"test-{random.randint(1000, 9999)}",
            "location": "Austin, TX",
            "collect_reviews": True,
        }

        with self.client.post(
            "/api/v1/collect",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/api/v1/collect"
        ) as response:
            if response.status_code in (200, 202, 404):
                response.success()
            else:
                response.failure(f"Collection trigger failed: {response.status_code}")

    @task(1)
    def request_analysis(self):
        """
        Request analysis for collected data.

        Weight: 1 (infrequent - computationally expensive)
        Expected: <2s for quick analysis
        """
        payload = {
            "business_id": f"test-{random.randint(1000, 9999)}",
            "analysis_type": "competitive",
        }

        with self.client.post(
            "/api/v1/analyze",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/api/v1/analyze"
        ) as response:
            if response.status_code in (200, 202, 404):
                response.success()
            else:
                response.failure(f"Analysis request failed: {response.status_code}")


class HeavyUser(HttpUser):
    """
    Simulates a power user making intensive API calls.

    Used to test system under stress from heavy users.
    """

    wait_time = between(0.5, 1)  # Faster request rate
    weight = 1  # Lower weight - fewer heavy users

    def on_start(self):
        """Setup for heavy user."""
        self.headers = {}

    @task(5)
    def rapid_health_checks(self):
        """Rapid health checks (monitoring system)."""
        self.client.get("/health", headers=self.headers)

    @task(3)
    def batch_collection(self):
        """Trigger multiple collections quickly."""
        for _ in range(3):
            payload = {
                "business_id": f"batch-{random.randint(1000, 9999)}",
                "location": "Austin, TX",
            }
            self.client.post(
                "/api/v1/collect",
                json=payload,
                headers=self.headers,
                name="/api/v1/collect [batch]"
            )


class MonitoringUser(HttpUser):
    """
    Simulates monitoring/observability systems polling endpoints.

    These are lightweight but frequent requests.
    """

    wait_time = between(5, 10)  # Poll every 5-10 seconds
    weight = 2

    @task
    def poll_health(self):
        """Health endpoint polling."""
        self.client.get("/health")

    @task
    def poll_metrics(self):
        """Metrics endpoint polling."""
        self.client.get("/metrics")


# Event hooks for custom reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("=" * 60)
    print("LocalPulse Load Test Starting")
    print(f"Host: {environment.host}")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("=" * 60)
    print("LocalPulse Load Test Complete")
    print("=" * 60)

    # Print summary statistics
    if environment.stats.total.num_requests > 0:
        stats = environment.stats.total
        print(f"\nTotal Requests: {stats.num_requests}")
        print(f"Failures: {stats.num_failures}")
        print(f"Failure Rate: {stats.fail_ratio * 100:.2f}%")
        print(f"Avg Response Time: {stats.avg_response_time:.2f}ms")
        print(f"Median Response Time: {stats.median_response_time}ms")
        print(f"95th percentile: {stats.get_response_time_percentile(0.95)}ms")
        print(f"99th percentile: {stats.get_response_time_percentile(0.99)}ms")
        print(f"Requests/sec: {stats.total_rps:.2f}")


# Custom shape for ramping up users (optional)
class StagesShape:
    """
    Custom load shape for staged ramp-up testing.

    Usage: locust -f locustfile.py --class-picker
    Then select StagesShape

    Stages:
    1. Warm-up: 10 users for 30s
    2. Normal load: 50 users for 60s
    3. Peak load: 100 users for 60s
    4. Cool-down: 25 users for 30s
    """

    stages = [
        {"duration": 30, "users": 10, "spawn_rate": 2},
        {"duration": 90, "users": 50, "spawn_rate": 5},
        {"duration": 150, "users": 100, "spawn_rate": 10},
        {"duration": 180, "users": 25, "spawn_rate": 5},
    ]

    def tick(self):
        """Return tuple (users, spawn_rate) or None to stop."""
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])

        return None
