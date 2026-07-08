## 2026-07-08 - Parallelize Data Fetching
**Learning:** Sequential network requests in data aggregation tasks create a performance bottleneck where total latency equals the sum of all individual request latencies. Parallelizing these requests reduces the total wait time to the duration of the slowest single request.
**Action:** Use `concurrent.futures.ThreadPoolExecutor` when multiple independent network-bound operations are required to assemble a final report.
