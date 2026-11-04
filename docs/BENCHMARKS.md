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
- The redirect handler checks Redis cache first; on cache hit it retrieves the target URL in sub-millisecond time.
- However, click tracking was performed via FastAPI's built-in `BackgroundTasks.add_task(track_click, ...)`.
- While the HTTP redirect response is emitted immediately by the ASGI loop, the in-process background task runs on the same event loop/thread pool, executing database queries (`SELECT`, `INSERT ClickEvent`, `UPDATE urls`) per redirect. Under 100 concurrent VUs, database connection acquisition and write contention saturate the process, resulting in elevated queueing and tail latencies.

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

*(This section will be populated after implementing Item 2 sliding-window rate limiting, Item 3 link management, and Item 4 asynchronous Redis Streams click analytics decoupled to `worker.py`.)*

| Metric | Baseline | After Optimizations | Delta |
|---|---|---|---|
| **Throughput (req/s)** | 89.63 req/s | TBD | TBD |
| **Error Rate** | 0.00% | TBD | TBD |
| **p50 Latency** | 470.91 ms | TBD | TBD |
| **p95 Latency** | 1,090.00 ms | TBD | TBD |
| **p99 Latency** | 1,230.00 ms | TBD | TBD |
| **Cache Hit Rate** | 100.0% | TBD | TBD |
