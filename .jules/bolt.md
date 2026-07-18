## 2026-05-10 - Mocking Python Requests for Connection Pooling

**Learning:** Mocking specific methods like `requests.Session.get` or `requests.Session.post` does not intercept top-level `requests.get` or `requests.post` calls. This is because the top-level functions instantiate a `Session` and directly invoke `Session.request(...)`, completely bypassing the specific `.get()` and `.post()` methods.

**Action:** When mocking network calls for both standard `requests` and custom `requests.Session()`-based modules, always patch the core `requests.Session.request` method. This single patch point guarantees interception of all requests, keeping tests robust and compatible across both sequential and connection-pooled code configurations.
