## 2026-07-13 - Parallel fetching and connection pooling
**Learning:** For a script that aggregates data from multiple I/O-bound API sources, using `ThreadPoolExecutor` and `requests.Session` provides a massive speedup (~4x in this case) with minimal code complexity.
**Action:** Always consider parallelizing network-bound operations and utilizing connection pooling for repeated API calls.
