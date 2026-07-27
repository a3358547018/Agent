# Bolt's Performance Journal

## 2025-02-18 - Thread-Safe requests.Session connection pooling with ThreadPoolExecutor
**Learning:** While sharing a single global `requests.Session()` across threads in a `ThreadPoolExecutor` can theoretically reuse connections, `requests.Session` is NOT thread-safe under parallel request execution. Concurrent threads using the same global session can experience race conditions, corrupted headers, or connection leaks.
**Action:** Use Python's `threading.local()` to store isolated `requests.Session` instances per thread. This combines the performance advantages of HTTP connection pooling within each individual worker thread with complete multi-threaded safety.
