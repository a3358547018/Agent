import unittest
from unittest.mock import MagicMock, patch
from datetime import date
import requests

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropPerformanceAndCorrectness(unittest.TestCase):

    def test_session_instances(self):
        """Verify that connection pooling sessions are correctly configured."""
        self.assertIsInstance(rootdata.session, requests.Session)
        self.assertIsInstance(cryptorank.session, requests.Session)
        self.assertIsInstance(okboost.session, requests.Session)
        self.assertIsInstance(notifier.session, requests.Session)

    @patch("requests.Session.request")
    def test_rootdata_fetching(self, mock_request):
        """Verify rootdata module functions handle mock JSON correctly."""
        # Mock Response
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "code": 200,
            "data": {
                "items": [
                    {
                        "project_name": "Test Project",
                        "amount": "$10M",
                        "round": "Series A",
                        "investors": ["VC A", "VC B"],
                        "date": "2026-07-19",
                        "url": "https://rootdata.com/test",
                        "description": "A test project description",
                    }
                ]
            }
        }
        mock_request.return_value = mock_resp

        # Test daily funding
        funding = rootdata.get_daily_funding(date(2026, 7, 19))
        self.assertEqual(len(funding), 1)
        self.assertEqual(funding[0]["name"], "Test Project")
        self.assertEqual(funding[0]["amount"], "$10M")

        # Test new projects
        mock_resp.json.return_value = {
            "code": 200,
            "data": {
                "items": [
                    {
                        "project_name": "New Project",
                        "tags": ["DeFi"],
                        "description": "New project desc",
                        "add_time": "2026-07-19",
                    }
                ]
            }
        }
        new_projects = rootdata.get_new_projects(1)
        self.assertEqual(len(new_projects), 1)
        self.assertEqual(new_projects[0]["name"], "New Project")

    @patch("requests.Session.request")
    def test_cryptorank_fetching(self, mock_request):
        """Verify cryptorank module functions handle mock JSON correctly."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": [
                {
                    "name": "CryptoRank Project",
                    "symbol": "CRP",
                    "amount": "$5M",
                    "stage": "Seed",
                    "investors": [{"name": "VC C"}],
                    "date": "2026-07-19",
                    "key": "cryptorank-project",
                }
            ]
        }
        mock_request.return_value = mock_resp

        funding = cryptorank.get_daily_funding(date(2026, 7, 19))
        self.assertEqual(len(funding), 1)
        self.assertEqual(funding[0]["name"], "CryptoRank Project")
        self.assertEqual(funding[0]["amount"], "$5M")

    @patch("requests.Session.request")
    def test_okboost_fetching(self, mock_request):
        """Verify okboost RSS parser with mock XML response."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.content = b"""<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>OKX Lists New Boost Mining</title>
              <link>https://www.okx.com/listing</link>
              <description>OKX launching new boost mining pool event</description>
              <pubDate>Sun, 19 Jul 2026 10:00:00 +0000</pubDate>
            </item>
          </channel>
        </rss>
        """
        mock_request.return_value = mock_resp

        # Set target date to July 19, 2026
        target_date = date(2026, 7, 19)
        events = okboost.get_daily_okboost(target_date)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "OKX Lists New Boost Mining")

    @patch("requests.Session.request")
    def test_notifier_send_chunk(self, mock_request):
        """Verify Telegram sender calls API correctly."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_request.return_value = mock_resp

        res = notifier._send_chunk("Test message")
        self.assertTrue(res)

    @patch("rootdata.get_daily_funding")
    @patch("rootdata.get_project_events")
    @patch("rootdata.get_new_projects")
    @patch("rootdata.get_upcoming_tge")
    @patch("cryptorank.get_daily_funding")
    @patch("cryptorank.get_upcoming_ido")
    @patch("okboost.get_daily_okboost")
    @patch("main.send_message")
    def test_run_daily_job_parallel(self, mock_send, mock_ok, mock_cr_ido, mock_cr_fund, mock_rd_tge, mock_rd_new, mock_rd_evt, mock_rd_fund):
        """Verify the parallel data job orchestrates and compiles daily report."""
        mock_rd_fund.return_value = [{"name": "P1", "amount": "$1M", "round": "Seed"}]
        mock_rd_evt.return_value = []
        mock_rd_new.return_value = []
        mock_rd_tge.return_value = []
        mock_cr_fund.return_value = []
        mock_cr_ido.return_value = []
        mock_ok.return_value = []

        # Run job
        main.run_daily_job()

        # Check that formatting was executed and sent
        self.assertTrue(mock_send.called)
        sent_report = mock_send.call_args[0][0]
        self.assertIn("P1", sent_report)
        self.assertIn("Seed", sent_report)


if __name__ == "__main__":
    unittest.main()
