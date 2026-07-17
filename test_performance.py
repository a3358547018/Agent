import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import time

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestPerformanceAndReuse(unittest.TestCase):
    @patch("rootdata._session")
    @patch("cryptorank._session")
    @patch("okboost._session")
    @patch("notifier._session")
    def test_parallel_execution_and_session_reuse(
        self, mock_notifier_session, mock_okboost_session, mock_cryptorank_session, mock_rootdata_session
    ):
        # 1. Setup mock responses with simulated latency (0.5s each) to verify parallel execution
        def slow_post(*args, **kwargs):
            time.sleep(0.5)
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"code": 200, "data": {}}
            return mock_resp

        def slow_get(*args, **kwargs):
            time.sleep(0.5)
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"data": {}}
            return mock_resp

        # Mock XML response for okboost RSS
        def slow_okboost_get(*args, **kwargs):
            time.sleep(0.5)
            mock_resp = MagicMock()
            mock_resp.content = b"<rss><channel></channel></rss>"
            return mock_resp

        mock_rootdata_session.post.side_effect = slow_post
        mock_cryptorank_session.get.side_effect = slow_get
        mock_okboost_session.get.side_effect = slow_okboost_get
        mock_notifier_session.post.return_value = MagicMock()

        # Measure performance of run_daily_job
        start_time = time.time()
        main.run_daily_job()
        end_time = time.time()
        elapsed_time = end_time - start_time

        print(f"\n⚡ Measured elapsed time for parallel run_daily_job: {elapsed_time:.4f}s")

        # 7 fetch tasks (4 rootdata, 2 cryptorank, 1 okboost) each with 0.5s simulated latency.
        # If execution was sequential, total execution time would be >= 3.5 seconds.
        # Since execution is parallel, it should finish in around ~0.5s to ~1.0s.
        self.assertLess(elapsed_time, 2.0, f"Expected elapsed time to be well under 2.0s, but got {elapsed_time:.4f}s")

        # 2. Verify Session reuse (the sessions must be called, proving they are utilized)
        self.assertGreaterEqual(mock_rootdata_session.post.call_count, 1)
        self.assertGreaterEqual(mock_cryptorank_session.get.call_count, 1)
        self.assertGreaterEqual(mock_okboost_session.get.call_count, 1)
        self.assertGreaterEqual(mock_notifier_session.post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
