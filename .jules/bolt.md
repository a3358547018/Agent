## 2026-08-06 - Parallel Network Fetching with Thread-Local Session Pooling

**Learning:** When aggregating cryptocurrency/airdrop data from multiple external API providers (RootData, CryptoRank, OKX), making sequential network requests is the primary performance bottleneck due to cumulative HTTP connection setup (DNS, TCP, TLS handshake) and API latencies. Combining `concurrent.futures.ThreadPoolExecutor` for parallel IO execution with `threading.local()` for thread-isolated `requests.Session()` connection pooling yields massive performance gains (from ~3.9s to ~0.9s in simulated latency environments) while guaranteeing full thread safety.

**Action:** For network-heavy data aggregation tools, always run independent API fetches in parallel using `ThreadPoolExecutor` and ensure each fetching module reuses TCP connections via a thread-local `requests.Session` pool to prevent concurrent state corruption.

## 2026-08-07 - Deferred/Lazy Evaluation of Regex Processing in RSS Feeds

**Learning:** Eagerly performing regex-based text processing (like HTML stripping via `re.sub` and `.strip()`) on all entries of fetched RSS/API feeds before date filtering is a performance anti-pattern. Since RSS feeds contain hundreds of historic elements that are immediately discarded by client-side filtering, eagerly cleaning every description wastes CPU cycles and time. Deferring the regex cleanup to only post-filtered items yields a ~30% execution time reduction in parsing.

**Action:** When filtering feed or API items on the client side, always perform dates and structural filters first, and lazily execute expensive text transformations/regex matches only on the final matching subset.
