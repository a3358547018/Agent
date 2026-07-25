# Bolt's Performance Journal

This journal is used to document critical performance-related learnings that help avoid mistakes or make better decisions in this codebase.

## 2026-07-25 - HTTP Connection Pooling & Concurrent Data Fetching
**Learning:** Sequential network-bound requests to external APIs suffer from high cumulative latency due to repeated TCP/TLS handshakes and blocking execution. Parallelizing requests using `ThreadPoolExecutor` and reusing connections with module-level `requests.Session()` reduces total run-time dramatically.
**Action:** Always check if multiple external API calls are independent, and if so, execute them concurrently while sharing a Session connection pool for identical hosts.
