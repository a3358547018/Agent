# Bolt's Journal

## 2026-07-20 - Connection Pooling & Mocking with Requests Session
**Learning:** When transitioning a codebase from standard procedural `requests.get` / `requests.post` calls to a connection-pooled `requests.Session()` design, standard mock-patching on `requests.get` or `requests.post` will miss any requests routed through `Session.get` or `Session.post`.
**Action:** When writing unit tests involving mock requests, patch `requests.Session.request` instead of individual methods like `get` or `post`, as it acts as a single integration point for both standard `requests` and `requests.Session` instances.
