import unittest
from unittest.mock import patch, MagicMock
from datetime import date, datetime

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestAirdropAgentPerformance(unittest.TestCase):

    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("notifier._get_session")
    @patch("main.send_message")
    def test_run_daily_job_parallel_execution(
        self,
        mock_send_message,
        mock_notifier_session_getter,
        mock_okboost_session_getter,
        mock_cryptorank_session_getter,
        mock_rootdata_session_getter,
    ):
        # 1. Setup Mock Sessions
        mock_rd_session = MagicMock()
        mock_cr_session = MagicMock()
        mock_ok_session = MagicMock()
        mock_notif_session = MagicMock()

        mock_rootdata_session_getter.return_value = mock_rd_session
        mock_cryptorank_session_getter.return_value = mock_cr_session
        mock_okboost_session_getter.return_value = mock_ok_session
        mock_notifier_session_getter.return_value = mock_notif_session

        # Mock RootData response
        mock_rd_resp = MagicMock()
        mock_rd_resp.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {"project_name": "Project A", "amount": "$10M", "round": "Series A"}
                ]
            }
        }
        mock_rd_session.post.return_value = mock_rd_resp

        # Mock CryptoRank response
        mock_cr_resp = MagicMock()
        mock_cr_resp.json.return_value = {
            "data": [
                {"name": "Project B", "amount": "$5M", "stage": "Seed"}
            ]
        }
        mock_cr_session.get.return_value = mock_cr_resp

        # Mock OKBoost response (XML RSS)
        pub_date_str = datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
        xml_content = f"""<rss><channel>
            <item>
                <title>New Launchpool Boost Announced</title>
                <link>https://okx.com/announcement/1</link>
                <description>Get high rewards staking OKB</description>
                <pubDate>{pub_date_str}</pubDate>
            </item>
        </channel></rss>""".encode("utf-8")

        mock_ok_resp = MagicMock()
        mock_ok_resp.content = xml_content
        mock_ok_session.get.return_value = mock_ok_resp

        # 2. Run the main daily job
        main.run_daily_job()

        # 3. Assertions to verify mock calls
        # Check that RootData POST calls were made
        self.assertTrue(mock_rd_session.post.called)
        # Check that CryptoRank GET calls were made
        self.assertTrue(mock_cr_session.get.called)
        # Check that OKBoost GET RSS calls were made
        self.assertTrue(mock_ok_session.get.called)

        # Check that telegram notifier sent the aggregated report
        self.assertTrue(mock_send_message.called)
        report_sent = mock_send_message.call_args[0][0]
        self.assertIn("Project A", report_sent)
        self.assertIn("Project B", report_sent)
        self.assertIn("Launchpool Boost", report_sent)

    def test_get_session_thread_safety_and_pooling(self):
        """Verify that _get_session returns a requests.Session instance and is thread-local."""
        import threading

        session1 = rootdata._get_session()
        self.assertIsInstance(session1, rootdata.requests.Session)

        # Verify it returns the same session on the same thread (pooling)
        session1_dup = rootdata._get_session()
        self.assertIs(session1, session1_dup)

        # Verify a different thread gets a different session instance (thread safety)
        other_session = []
        def run_thread():
            other_session.append(rootdata._get_session())

        t = threading.Thread(target=run_thread)
        t.start()
        t.join()

        self.assertNotEqual(id(session1), id(other_session[0]))


if __name__ == "__main__":
    unittest.main()
