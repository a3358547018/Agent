import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import requests

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropDiscoveryOptimizations(unittest.TestCase):

    def test_requests_session_used_in_modules(self):
        """Verify that the module-level _session is indeed an instance of requests.Session."""
        self.assertIsInstance(rootdata._session, requests.Session)
        self.assertIsInstance(cryptorank._session, requests.Session)
        self.assertIsInstance(okboost._session, requests.Session)
        self.assertIsInstance(notifier._session, requests.Session)

    @patch('requests.Session.request')
    def test_run_daily_job_parallel_execution(self, mock_request):
        """
        Verify that run_daily_job executes completely and without error,
        calling the underlying requests.Session.request.
        """
        # Configure a dummy successful JSON response for all POST/GET requests
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"code": 200, "data": {"items": [], "list": []}}
        mock_response.content = b"<rss><channel><item><title>Mock Boost</title><description>Earn rewards</description><link>https://okx.com</link><pubDate>Thu, 23 Jul 2026 10:00:00 GMT</pubDate></item></channel></rss>"
        mock_request.return_value = mock_response

        # Execute run_daily_job and ensure it doesn't crash
        try:
            main.run_daily_job()
        except Exception as e:
            self.fail(f"run_daily_job raised an exception: {e}")

        # Ensure we made several API requests
        self.assertTrue(mock_request.call_count >= 7)


if __name__ == "__main__":
    unittest.main()
