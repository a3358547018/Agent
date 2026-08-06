## 2026-08-06 - Parallel Network Fetching with Thread-Local Session Pooling

**Learning:** When aggregating cryptocurrency/airdrop data from multiple external API providers (RootData, CryptoRank, OKX), making sequential network requests is the primary performance bottleneck due to cumulative HTTP connection setup (DNS, TCP, TLS handshake) and API latencies. Combining `concurrent.futures.ThreadPoolExecutor` for parallel IO execution with `threading.local()` for thread-isolated `requests.Session()` connection pooling yields massive performance gains (from ~3.9s to ~0.9s in simulated latency environments) while guaranteeing full thread safety.

**Action:** For network-heavy data aggregation tools, always run independent API fetches in parallel using `ThreadPoolExecutor` and ensure each fetching module reuses TCP connections via a thread-local `requests.Session` pool to prevent concurrent state corruption.
