## 2026-07-09 - Parallelized Data Fetching and Connection Pooling
**Learning:** The application was performing 7 independent network-bound operations sequentially in `main.py`, leading to a total latency equal to the sum of individual request times. Additionally, every API call was creating a new TCP/TLS connection.
**Action:** Use `concurrent.futures.ThreadPoolExecutor` for parallel data fetching and `requests.Session()` for HTTP connection pooling to significantly reduce execution time and resource overhead.
