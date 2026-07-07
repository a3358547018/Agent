# Bolt's Journal - Critical Learnings

## 2026-07-07 - Parallelizing I/O-bound API Aggregators
**Learning:** In data aggregator applications like this one, sequential network requests are the primary bottleneck. Latency accumulates linearly ($O(n)$), making the app feel sluggish even if the data volume is small.
**Action:** Always check for independent I/O operations in the main execution path. Use `concurrent.futures.ThreadPoolExecutor` for a low-overhead way to parallelize these calls in Python without significant architectural changes.
