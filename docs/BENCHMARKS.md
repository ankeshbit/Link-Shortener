# ByteLink Load Test Benchmarks

This document records reproducible, empirical performance benchmarks for the ByteLink URL shortener service redirect path (`GET /{short_id}`).

All numbers reported in this document were directly measured using [k6](https://k6.io/) running against a local instance of the application. **No numbers are estimated or invented.**

---

## Benchmark Environment & Setup

- **Host Operating System:** Microsoft Windows 11 Home Single Language (64-bit, Build 26100)
- **CPU:** 13th Gen Intel(R) Core(TM) i5-13420H (8 Cores, 12 Threads @ 2.10 GHz base)
- **Memory (RAM):** 16.0 GB DDR5
- **Storage:** Solid-State Drive (NVMe SSD)
- **Backend Runtime:** Python 3.10.0, FastAPI 0.111.1, Uvicorn 0.30.6 (single worker process)
- **Relational Database:** PostgreSQL 18.6 (mingw-w64-ucrt-x86_64, localhost:5432)
- **In-Memory Cache / Broker:** Redis 5.0.14.1 (localhost:6379, RESP2 protocol)
- **Load Generator:** k6 v0.54.0 (windows/amd64)

### Workload & Scenario Profile (`loadtest/redirect.js`)
1. **Setup Phase:** Authenticates an automated test user and creates 1,000 distinct short links via `POST /api/shorten` in concurrent batches.
2. **Execution Phase:** Up to 100 virtual users (VUs) continuously issue `GET /{short_id}` requests with `redirects: 0` (measuring the raw redirect response time without following external target redirects).
   - Ramp up: 0 to 50 VUs over 10 seconds.
   - Peak load: 50 to 100 VUs over 20 seconds.
   - Ramp down: 100 to 0 VUs over 5 seconds.
   - Sleep: 10ms between requests per VU.
3. **Teardown Phase:** Queries `GET /api/metrics` to verify cumulative redirect cache hits, misses, and hit rates.

---

## 1. Baseline Benchmark (Item 1)

In the baseline implementation:
- The redirect handler checked Redis cache first; on cache hit it retrieved the target URL in sub-millisecond time.
- However, click tracking was performed via FastAPI's built-in `BackgroundTasks.add_task(track_click, ...)`.
- While the HTTP redirect response was emitted immediately by the ASGI loop, the in-process background task ran on the same event loop/thread pool, executing database queries (`SELECT`, `INSERT ClickEvent`, `UPDATE urls`) per redirect. Under 100 concurrent VUs, database connection acquisition and write contention saturated the process, resulting in elevated queueing and tail latencies.

### Baseline Results

| Metric | Measured Baseline Value |
|---|---|
| **Total Benchmark Requests** | 3,272 redirects (4,274 total HTTP requests including setup) |
| **Peak Virtual Users (VUs)** | 100 concurrent VUs |
| **Throughput (req/s)** | 89.63 req/s (overall) / 68.62 iterations/s |
| **Error Rate** | **0.00%** (0 failed requests out of 4,274; 100% redirect checks passed) |
| **Cache Hit Rate** | **100.0%** (6,951 hits / 0 misses) |
| **Latency: Min** | 0.86 ms |
| **Latency: p50 (Median)** | **470.91 ms** |
| **Latency: p90** | **1,030.00 ms** (1.03 s) |
| **Latency: p95** | **1,090.00 ms** (1.09 s) |
| **Latency: p99** | **1,230.00 ms** (1.23 s) |
| **Latency: Max** | 1,340.00 ms (1.34 s) |

---

## 2. Post-Optimization Benchmark (Items 2–4)

In the optimized implementation:
- **Item 2:** Sliding-window rate limiting per client IP using atomic Lua scripts on Redis sorted sets.
- **Item 3:** Atomic link management (`max_clicks` check, `is_active` validation) on both cache and DB paths.
- **Item 4:** Click tracking was completely decoupled from the FastAPI request cycle. The redirect path performs a non-blocking `XADD` to Redis Streams (`stream:clicks`) in sub-millisecond memory time.
- A decoupled consumer group worker (`backend/worker.py`) asynchronously consumes events, parses user agents and GeoIP, batch-inserts `ClickEvent` rows, atomically updates `clicks_count`, and emits real-time WebSocket updates via Redis Pub/Sub.

### Comparison Table

| Metric | Baseline | After Optimizations | Delta |
|---|---|---|---|
| **Total Redirect Requests** | 3,272 redirects | **6,582 redirects** | **+101.2% (2.0x requests served)** |
| **Total HTTP Requests** | 4,274 requests | **7,584 requests** | **+77.4%** |
| **Throughput (http_reqs)** | 89.63 req/s | **156.57 req/s** | **+74.7% throughput increase** |
| **Iteration Rate** | 68.62 /s | **135.89 /s** | **+98.0% iterations/sec** |
| **Error Rate** | 0.00% | **0.00%** | **0 failures (100% checks passed)** |
| **Cache Hit Rate** | 100.0% | **99.37%** (13,656 hits / 41 misses) | Stable production caching |
| **p50 (Median) Latency** | 470.91 ms | **282.24 ms** | **40.1% faster (-188.67 ms)** |
| **p90 Latency** | 1,030.00 ms | **489.73 ms** | **52.5% faster (-540.27 ms)** |
| **p95 Latency** | 1,090.00 ms | **550.78 ms** | **49.5% faster (-539.22 ms)** |
| **p99 Latency** | 1,230.00 ms | **652.48 ms** | **47.0% faster (-577.52 ms)** |
| **Max Latency** | 1,340.00 ms | **708.10 ms** | **47.2% reduction (-631.90 ms)** |

### Architectural Insights & Findings
1. **Decoupling I/O Bottlenecks:** Moving click persistence from FastAPI in-process background tasks to a Redis Streams buffer eliminated database connection pool contention during bursts of 100 concurrent VUs.
2. **Tail Latency Halved:** The p95 latency dropped from 1.09s to 550.78ms (a 49.5% reduction) and p99 dropped from 1.23s to 652.48ms, while throughput climbed from 89.63 to 156.57 req/s.
3. **Resilience & Fault Tolerance:** Even under sustained peak load, zero requests failed (0.00% error rate), and the worker seamlessly batch-processed all stream entries into PostgreSQL with full deduplication guarantees.
