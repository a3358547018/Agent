## 2025-05-15 - Optimize data fetching with parallelization and connection pooling
**Learning:** Network-bound I/O is the primary bottleneck in this cryptocurrency discovery assistant. Sequential API calls to RootData, CryptoRank, and OKX RSS can be significantly speed up by using parallel execution and HTTP connection pooling.
**Action:** Use `ThreadPoolExecutor` for parallel data fetching in `main.py` and `requests.Session()` in data modules to reuse TCP connections.
