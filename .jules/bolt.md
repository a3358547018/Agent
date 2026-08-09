# Bolt's Journal

## 2026-08-09 - Parallelizing I/O-Bound API Calls with ThreadPoolExecutor & Thread-Local Sessions
**Learning:** Sequential network-bound requests to RootData, CryptoRank, and OKX RSS cause significant latency overhead. Parallelizing them using a ThreadPoolExecutor decreases execution time from ~3.9s to ~0.9s under simulated high-latency. Using thread-local requests.Session ensures concurrency-safe, pooled HTTP connections.
**Action:** Use concurrent.futures.ThreadPoolExecutor for parallel API fetching, and thread-local session management to prevent race conditions during concurrent requests.
