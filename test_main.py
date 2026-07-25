import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import requests

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropDiscoveryPerformance(unittest.TestCase):

    @patch("requests.Session.request")
    def test_rootdata_get_daily_funding_success(self, mock_request):
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {
                        "project_name": "TestProj",
                        "amount": "$10M",
                        "round": "Seed",
                        "investors": ["VC A", "VC B"],
                        "date": "2026-07-25",
                        "url": "https://test.url",
                        "description": "A very cool project"
                    }
                ]
            }
        }
        mock_request.return_value = mock_response

        # Act
        result = rootdata.get_daily_funding(date(2026, 7, 25))

        # Assert
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "TestProj")
        self.assertEqual(result[0]["amount"], "$10M")
        self.assertEqual(result[0]["round"], "Seed")
        self.assertEqual(result[0]["investors"], ["VC A", "VC B"])

    @patch("requests.Session.request")
    def test_cryptorank_get_daily_funding_success(self, mock_request):
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "name": "CryptoProj",
                    "symbol": "CP",
                    "amount": 5000000,
                    "stage": "Series A",
                    "investors": [{"name": "Fund X"}],
                    "date": "2026-07-25",
                    "key": "cryptoproj"
                }
            ]
        }
        mock_request.return_value = mock_response

        # Act
        result = cryptorank.get_daily_funding(date(2026, 7, 25))

        # Assert
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "CryptoProj")
        self.assertEqual(result[0]["amount"], 5000000)
        self.assertEqual(result[0]["round"], "Series A")
        self.assertEqual(result[0]["investors"], ["Fund X"])

    @patch("requests.Session.request")
    def test_okboost_get_daily_okboost_success(self, mock_request):
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""<rss version="2.0">
          <channel>
            <title>OKX Support</title>
            <item>
              <title>OKX launches new boost event</title>
              <link>https://www.okx.com/help-center/boost</link>
              <description>&lt;p&gt;We are launching a new boost staking event with great rewards!&lt;/p&gt;</description>
              <pubDate>Sat, 25 Jul 2026 12:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""
        mock_request.return_value = mock_response

        # Act
        result = okboost.get_daily_okboost(date(2026, 7, 25))

        # Assert
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "OKX launches new boost event")
        self.assertTrue("boost" in result[0]["desc"].lower())

    @patch("requests.Session.request")
    def test_notifier_send_message_truncation_and_escaping(self, mock_request):
        # Arrange
        mock_response = MagicMock()
        mock_response.ok = True
        mock_request.return_value = mock_response

        # Act
        # High level formatting test
        report = notifier.fmt_daily_report(
            rd_funding=[{"name": "<a>Test</a>", "round": "Seed", "amount": "$1M", "url": "http://test", "investors": ["VC"]}],
            rd_events=[],
            rd_new_proj=[],
            rd_tge=[],
            cr_funding=[],
            cr_ido=[],
            okboost=[],
            report_date="2026-07-25"
        )

        # Verify formatting escapes tags in project names
        self.assertIn("&lt;a&gt;Test&lt;/a&gt;", report)

        # Test segmenting long messages
        long_message = "Paragraph\n\n" * 500
        notifier.send_message(long_message)

        # Verify mock_request was called (meaning notifier worked and sent segments)
        self.assertTrue(mock_request.called)

    @patch("requests.Session.request")
    def test_run_daily_job_concurrently_success(self, mock_request):
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True

        # Return generic simple structures for different queries
        def mock_request_side_effect(method, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.ok = True
            if "rootdata" in url:
                resp.json.return_value = {"result": True, "data": []}
            elif "cryptorank" in url:
                resp.json.return_value = {"data": []}
            elif "okx" in url:
                resp.content = b"<rss><channel></channel></rss>"
            elif "telegram" in url:
                resp.json.return_value = {"ok": True}
            return resp

        mock_request.side_effect = mock_request_side_effect

        # Act & Assert - should run successfully without raising any exceptions
        try:
            main.run_daily_job()
        except Exception as e:
            self.fail(f"run_daily_job failed concurrently: {e}")


if __name__ == "__main__":
    unittest.main()
