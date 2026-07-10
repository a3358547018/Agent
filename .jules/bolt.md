## 2024-05-24 - Parallel Fetching & Connection Pooling
**Learning:** Sequential network-bound tasks in the main loop were the primary bottleneck. Using 'ThreadPoolExecutor' for independent API calls and 'requests.Session()' for connection reuse significantly improves execution speed and efficiency.
**Action:** Always look for independent I/O operations that can be parallelized and ensure persistent connections are used for repeated requests to the same hosts.
