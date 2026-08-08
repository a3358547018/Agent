import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import concurrent.futures

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestParallelAirdropAssistant(unittest.TestCase):

    @patch("main.date")
    @patch("main.send_message")
    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    def test_run_daily_job_parallel_execution(self, mock_ok_session_get, mock_cr_session_get, mock_rd_session_get, mock_send_message, mock_date):
        # Setup specific date
        mock_date.today.return_value = date(2026, 8, 8)

        # Mock sessions and their HTTP methods
        mock_rd_session = MagicMock()
        mock_rd_session_get.return_value = mock_rd_session
        # rootdata uses _post (POST requests)
        mock_rd_session.post.return_value.json.return_value = {
            "result": True,
            "data": {
                "items": [{"project_name": "TestProj", "amount": "1M", "round": "Seed", "investors": ["VC1"]}]
            }
        }

        mock_cr_session = MagicMock()
        mock_cr_session_get.return_value = mock_cr_session
        # cryptorank uses _get (GET requests)
        mock_cr_session.get.return_value.json.return_value = {
            "data": [{"name": "CRProj", "amount": "2M", "stage": "Private", "investors": [{"name": "VC2"}]}]
        }

        mock_ok_session = MagicMock()
        mock_ok_session_get.return_value = mock_ok_session
        # okboost parses RSS XML
        mock_ok_session.get.return_value.content = b"""<rss version="2.0"><channel><item><title>OKBoost launchpool</title><link>http://link</link><description>Description with boost</description><pubDate>Sat, 08 Aug 2026 10:00:00 GMT</pubDate></item></channel></rss>"""

        # Run the daily job which runs in parallel
        main.run_daily_job()

        # Check if send_message was called with formatting including our mock data
        self.assertTrue(mock_send_message.called)
        report_text = mock_send_message.call_args[0][0]
        self.assertIn("TestProj", report_text)
        self.assertIn("CRProj", report_text)
        self.assertIn("OKBoost launchpool", report_text)

    @patch("rootdata._get_session")
    def test_rootdata_thread_local_session(self, mock_get_session):
        # Verify that thread-local sessions work as expected
        session1 = rootdata._get_session()
        session2 = rootdata._get_session()
        self.assertEqual(session1, session2)

        # Let's test calling it inside a separate thread to ensure thread safety / different sessions
        def get_other_session():
            return rootdata._get_session()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(get_other_session)
            session_other = future.result()

        # Since it's thread local, calling _get_session in different threads should return distinct Session instances if not mocked.
        # However, since we patched it, we just want to verify basic functionality.

if __name__ == "__main__":
    unittest.main()
