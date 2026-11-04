# ByteLink Load Testing Suite

This directory contains automated k6 load tests for evaluating ByteLink's high-throughput redirect path, Redis caching efficiency, and system latency under concurrency.

## Prerequisites

1. **PostgreSQL**: Running and accessible via `DATABASE_URL` (local or Neon).
2. **Redis**: Running on `127.0.0.1:6379` (local or hosted).
3. **ByteLink Backend**: Running on `http://127.0.0.1:8000`:
   ```powershell
   cd backend
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
4. **k6**: Installed locally ([k6 installation guide](https://k6.io/docs/get-started/installation/)).

## Running the Redirect Load Test

Run the test using k6:

```powershell
k6 run loadtest/redirect.js
```

To target a different server host or port:

```powershell
k6 run -e BASE_URL=http://localhost:8000 loadtest/redirect.js
```

## How the Load Test Works

1. **Setup Phase (`setup()`)**:
   - Registers a dedicated benchmark user (`POST /api/auth/register`).
   - Generates ~1,000 unique test links via batched HTTP requests (`POST /api/shorten`).
   - Stores the generated short IDs in memory and passes them to the virtual users.

2. **Workload Phase (`default()`)**:
   - Simulates ramping concurrency:
     - 0 to 50 virtual users (VUs) over 10 seconds.
     - 50 to 100 VUs sustained over 20 seconds.
     - 100 to 0 VUs ramp-down over 5 seconds.
   - Each virtual user selects a random short link from the pool of 1,000 links and issues `GET /{short_id}` with `redirects: 0` (no follow-redirects).
   - Validates that every response returns an HTTP redirect status (`301`, `302`, `303`, or `307`).

3. **Teardown Phase (`teardown()`)**:
   - Queries `GET /api/metrics` to report the final cache hit rate, total redirects processed, and cache misses.

## Observing Metrics During Test

You can observe live metrics at any time by querying:

```powershell
curl http://127.0.0.1:8000/api/metrics
```

Output:
```json
{
  "total_redirects": 24500,
  "cache_hits": 24200,
  "cache_misses": 300,
  "cache_hit_rate": 0.9878
}
```
