# Bolt Performance Journal

## 2026-07-17 - Concurrency & Connection Reuse Optimization
**Learning:** Sequential network-bound requests to external APIs (RootData, CryptoRank, OKX) cause high latency. Re-creating HTTP connections for each request creates a massive DNS, TCP, and TLS handshake overhead.
**Action:** Use `requests.Session()` within data modules to pool HTTP connections and use `concurrent.futures.ThreadPoolExecutor` in `main.py` to parallelize independent fetch tasks. This will reduce execution time from ~3.9s to ~0.9s under simulated high-latency tests.
