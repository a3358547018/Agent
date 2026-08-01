# Bolt's Journal

## 2026-08-01 - Test Environment Package Resolution
**Learning:** Pytest invoked globally may resolve to the system python environment, leading to `ModuleNotFoundError` for packages installed in the local virtual/pyenv environment.
**Action:** Always prefer running tests using standard `python -m unittest` or `python -m pytest` inside the correct pyenv/virtual environment to avoid dependency mismatch.
