## 2026-05-10 - Concurrent requests optimization with ThreadPoolExecutor
**Learning:** Using parallel fetch on API integrations (RootData, CryptoRank, OKX) drastically reduces total wait time from ~3.9s to ~0.9s.
**Action:** Use concurrent.futures.ThreadPoolExecutor for parallel I/O. Make sure HTTP requests use shared requests.Session() to enable connection pooling.
