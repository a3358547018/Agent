import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import sys

# Ensure project root is in path
sys.path.insert(0, ".")

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestAirdropDiscoveryAssistant(unittest.TestCase):

    def setUp(self):
        # Create mock responses for testing
        self.mock_session_inst = MagicMock()

        # Configure the session mocks
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200
        self.mock_response.ok = True

        # Default behavior: mock JSON responses
        self.mock_response.json.return_value = {"code": 200, "result": True, "data": []}
        self.mock_session_inst.get.return_value = self.mock_response
        self.mock_session_inst.post.return_value = self.mock_response

    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("notifier._get_session")
    def test_run_daily_job_success(self, mock_notifier_sess, mock_ok_sess, mock_cr_sess, mock_rd_sess):
        # Configure mocked thread-local sessions
        mock_rd_sess.return_value = self.mock_session_inst
        mock_cr_sess.return_value = self.mock_session_inst
        mock_ok_sess.return_value = self.mock_session_inst
        mock_notifier_sess.return_value = self.mock_session_inst

        # Mock API responses
        # OKBoost RSS feed XML response
        mock_xml_resp = MagicMock()
        mock_xml_resp.status_code = 200
        mock_xml_resp.ok = True
        mock_xml_resp.content = b'<rss><channel><item><title>Test OKX Announcement</title><link>https://okx.com</link><description>Description here</description><pubDate>Mon, 10 Aug 2026 12:00:00 GMT</pubDate></item></channel></rss>'

        def side_effect_get(url, *args, **kwargs):
            if "rss.xml" in url:
                return mock_xml_resp
            # Standard CryptoRank mock json
            resp = MagicMock()
            resp.status_code = 200
            resp.ok = True
            resp.json.return_value = {
                "data": [
                    {
                        "name": "Test CryptoRank Project",
                        "symbol": "TCR",
                        "amount": "1000000",
                        "stage": "Seed",
                        "investors": [{"name": "VC Fund"}]
                    }
                ]
            }
            return resp

        def side_effect_post(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.ok = True
            if "api.telegram.org" in url:
                resp.json.return_value = {"ok": True}
            else:
                resp.json.return_value = {
                    "code": 200,
                    "result": True,
                    "data": {
                        "items": [
                            {
                                "project_name": "Test RootData Project",
                                "amount": "5000000",
                                "round": "Series A",
                                "investors": ["Top VC"]
                            }
                        ]
                    }
                }
            return resp

        self.mock_session_inst.get.side_effect = side_effect_get
        self.mock_session_inst.post.side_effect = side_effect_post

        # Let's fix today's date in okboost to match the RSS's date (August 10, 2026)
        with patch("okboost.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 10)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            # Let's run daily job
            with patch("main.send_message") as mock_send:
                main.run_daily_job()

                # Check that send_message was called with the report
                mock_send.assert_called_once()
                report_text = mock_send.call_args[0][0]

                # Verify that both the mocked RootData project and CryptoRank project are in the report text!
                self.assertIn("Test RootData Project", report_text)
                self.assertIn("Test CryptoRank Project", report_text)

    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("notifier._get_session")
    def test_run_daily_job_handles_individual_errors(self, mock_notifier_sess, mock_ok_sess, mock_cr_sess, mock_rd_sess):
        """Even if some fetching calls throw exceptions, others should succeed and report should still compile."""
        mock_rd_sess.return_value = self.mock_session_inst
        mock_cr_sess.return_value = self.mock_session_inst
        mock_ok_sess.return_value = self.mock_session_inst
        mock_notifier_sess.return_value = self.mock_session_inst

        # Throw exception for RootData post, but let CryptoRank succeed
        def side_effect_post(url, *args, **kwargs):
            if "api.telegram.org" in url:
                resp = MagicMock()
                resp.status_code = 200
                resp.ok = True
                resp.json.return_value = {"ok": True}
                return resp
            raise RuntimeError("RootData API is down!")

        def side_effect_get(url, *args, **kwargs):
            if "rss.xml" in url:
                raise RuntimeError("RSS URL has timeout")
            resp = MagicMock()
            resp.status_code = 200
            resp.ok = True
            resp.json.return_value = {
                "data": [
                    {
                        "name": "Succeeding CryptoRank",
                        "symbol": "SCR",
                        "amount": "2000000",
                        "stage": "Private"
                    }
                ]
            }
            return resp

        self.mock_session_inst.get.side_effect = side_effect_get
        self.mock_session_inst.post.side_effect = side_effect_post

        with patch("main.send_message") as mock_send:
            main.run_daily_job()

            mock_send.assert_called_once()
            report_text = mock_send.call_args[0][0]

            # RootData parts should display daily empty info
            self.assertIn("今日暂无 RootData 融资数据", report_text)
            # CryptoRank part should still display Succeeding CryptoRank!
            self.assertIn("Succeeding CryptoRank", report_text)


if __name__ == "__main__":
    unittest.main()
