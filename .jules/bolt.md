## 2026-07-15 - Parallelizing Data Fetching
**Learning:** Sequential API calls in the main job were causing a bottleneck (~4s execution).
**Action:** Implementing ThreadPoolExecutor to parallelize independent network-bound tasks.
