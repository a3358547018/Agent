# Bolt's Journal - Critical Learnings

## 2026-08-11 - ThreadPoolExecutor & Thread-Local Sessions Optimization
**Learning:** Sequential network requests to external APIs (RootData, CryptoRank, OKX) cause high latency. Parallelizing requests using `concurrent.futures.ThreadPoolExecutor` and reusing connections with a thread-local `requests.Session` avoids connection overhead and race conditions while drastically improving performance.
**Action:** Use `threading.local` to manage a per-thread `requests.Session` across parallel worker threads.
