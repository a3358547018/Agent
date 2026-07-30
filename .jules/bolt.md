# ⚡ Bolt's Performance Journal

## 2025-07-30 - Thread-Local Connection Pooling in Concurrent Environments
**Learning:** Standard HTTP client requests (e.g., using `requests` directly) open and close TCP connections for each request, adding significant latency. Reusing connection pools via `requests.Session` is highly effective, but sharing a single `requests.Session` object across multiple threads executing concurrently with `ThreadPoolExecutor` can cause race conditions and corrupted data/headers.
**Action:** Use thread-local `requests.Session` instances backed by `threading.local()` inside each data fetching module. This ensures thread safety during concurrent executions while still maximizing connection reuse benefits per thread.
