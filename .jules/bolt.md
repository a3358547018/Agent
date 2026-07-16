## 2026-07-16 - Parallel Data Fetching & Connection Pooling
**Learning:** Parallelizing independent network-bound API calls in Python using `ThreadPoolExecutor` and enabling connection pooling with `requests.Session()` can reduce execution time by over 80% for data-heavy orchestration tasks.
**Action:** Always check for sequential network requests in main loops or job orchestrators and consider `ThreadPoolExecutor` for I/O bound tasks. Use `requests.Session()` per module or host to leverage Keep-Alive.
