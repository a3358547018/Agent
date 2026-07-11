## 2026-07-11 - Parallelization and Connection Pooling
**Learning:** For applications heavily dependent on multiple independent API calls, sequential fetching becomes a major bottleneck. Implementing `concurrent.futures.ThreadPoolExecutor` for parallel fetching and `requests.Session()` for HTTP connection pooling significantly reduces latency by overlapping network I/O and reusing established TCP connections.
**Action:** Always look for independent network-bound operations that can be parallelized and ensure persistent HTTP sessions are used for repeated requests to the same domains.
