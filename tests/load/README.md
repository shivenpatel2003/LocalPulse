# LocalPulse Load Testing

Load tests using [Locust](https://locust.io/) to verify system performance and throughput.

## Quick Start

### Prerequisites

```bash
# Install dependencies (locust is in dev dependencies)
poetry install
```

### Running Tests

**With Web UI:**
```bash
# Start the API server first
poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# In another terminal, start Locust
poetry run locust -f tests/load/locustfile.py --host=http://localhost:8000
```

Then open http://localhost:8089 in your browser.

**Headless (CI/CD):**
```bash
poetry run locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --headless \
    --users 50 \
    --spawn-rate 10 \
    --run-time 60s \
    --csv=results/load_test
```

## User Classes

### LocalPulseUser (Default)
Simulates typical user behavior:
- Health checks (frequent)
- Metrics polling
- Business listing
- Collection triggers (occasional)
- Analysis requests (rare)

### HeavyUser
Simulates power users with intensive API usage:
- Rapid health checks
- Batch collection requests

### MonitoringUser
Simulates monitoring systems:
- Periodic health endpoint polling
- Metrics endpoint polling

## Expected Performance Baselines

| Endpoint | Method | p95 Target | p99 Target |
|----------|--------|------------|------------|
| /health | GET | <50ms | <100ms |
| /metrics | GET | <100ms | <200ms |
| /api/v1/businesses | GET | <200ms | <500ms |
| /api/v1/collect | POST | <500ms | <1s |
| /api/v1/analyze | POST | <2s | <5s |

## Test Scenarios

### Normal Load Test
```bash
# 50 users, 60 seconds
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
    --headless -u 50 -r 10 -t 60s
```

### Stress Test
```bash
# 200 users, 5 minutes
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
    --headless -u 200 -r 20 -t 5m
```

### Soak Test
```bash
# 50 users, 30 minutes
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
    --headless -u 50 -r 5 -t 30m
```

## Interpreting Results

### Key Metrics

- **Requests/sec (RPS)**: Throughput - higher is better
- **Response time p95/p99**: Latency percentiles - lower is better
- **Failure rate**: Should be <1% under normal load

### Warning Signs

- p99 > 2x p95: Indicates inconsistent performance
- Failure rate > 1%: Endpoint may be struggling
- RPS decreasing over time: Possible resource leak

## Configuration

### Environment Variables

For authenticated endpoints:
```bash
export LOCALPULSE_API_KEY="your-api-key"
```

### Distributed Testing

For higher load, run Locust in distributed mode:

**Master:**
```bash
locust -f tests/load/locustfile.py --master
```

**Workers:**
```bash
locust -f tests/load/locustfile.py --worker --master-host=<master-ip>
```

## CI/CD Integration

Example GitHub Actions step:
```yaml
- name: Run Load Tests
  run: |
    poetry run locust -f tests/load/locustfile.py \
      --host=http://localhost:8000 \
      --headless \
      --users 50 \
      --spawn-rate 10 \
      --run-time 60s \
      --csv=results/load_test \
      --exit-code-on-error 1
```

## Output Files

When using `--csv=results/load_test`:
- `load_test_stats.csv`: Per-endpoint statistics
- `load_test_stats_history.csv`: Time series data
- `load_test_failures.csv`: Failure details
- `load_test_exceptions.csv`: Python exceptions

## Troubleshooting

### "Connection refused"
Ensure the API server is running on the specified host/port.

### "Too many open files"
Increase ulimit: `ulimit -n 10000`

### Inconsistent results
- Run tests multiple times
- Ensure no other processes are using significant resources
- Check for rate limiting
