# Bolt's Journal - Critical Learnings

## 2026-07-24 - Mocking HTTP Connections and Module Sessions
**Learning:** When using module-level `requests.Session` for connection pooling, unit tests that mock individual requests calls (like `requests.get` or `requests.post`) will fail to intercept HTTP requests because the code calls the session's internal request method. Therefore, we should patch `requests.Session.request` directly.
**Action:** Always patch `requests.Session.request` to intercept and mock connection-pooled requests correctly.
