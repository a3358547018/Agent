import unittest
from unittest.mock import MagicMock, patch
from datetime import date

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestAirdropHelperParallel(unittest.TestCase):

    def setUp(self):
        # Set up a generic mock session
        self.mock_session_rd = MagicMock()
        self.mock_session_cr = MagicMock()
        self.mock_session_ok = MagicMock()
        self.mock_session_nt = MagicMock()

    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("notifier._get_session")
    @patch("main.send_message")
    def test_run_daily_job_success(self, mock_send_message, mock_get_session_nt, mock_get_session_ok, mock_get_session_cr, mock_get_session_rd):
        # Configure mocks to return custom mock session objects
        mock_get_session_rd.return_value = self.mock_session_rd
        mock_get_session_cr.return_value = self.mock_session_cr
        mock_get_session_ok.return_value = self.mock_session_ok
        mock_get_session_nt.return_value = self.mock_session_nt

        # Mock RootData responses
        mock_resp_rd_invest = MagicMock()
        mock_resp_rd_invest.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {"project_name": "ProjectA", "amount": "1M", "round": "Seed", "lead_investors": ["VC_A"]}
                ]
            }
        }

        mock_resp_rd_pro = MagicMock()
        mock_resp_rd_pro.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {"project_name": "NewProjB", "tags": ["DeFi"], "description": "Awesome project"}
                ]
            }
        }

        mock_resp_rd_calendar = MagicMock()
        mock_resp_rd_calendar.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {"project_name": "EventC", "event_name": "Mainnet Launch", "date": "2026-08-06"}
                ]
            }
        }

        mock_resp_rd_unlock = MagicMock()
        mock_resp_rd_unlock.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {"project_name": "TokenD", "tge_date": "2026-08-07", "symbol": "D", "total_raise": "500k"}
                ]
            }
        }

        # RootData uses POST. Let's make post return different mock responses depending on endpoint.
        def mock_post_rd(url, json, headers, timeout):
            resp = MagicMock()
            if "/get_invest_list" in url:
                return mock_resp_rd_invest
            elif "/get_pro_list" in url:
                return mock_resp_rd_pro
            elif "/get_calendar_list" in url:
                return mock_resp_rd_calendar
            elif "/get_token_unlock" in url:
                return mock_resp_rd_unlock
            return resp

        self.mock_session_rd.post.side_effect = mock_post_rd

        # Mock CryptoRank responses
        mock_resp_cr_funding = MagicMock()
        mock_resp_cr_funding.json.return_value = {
            "data": [
                {"name": "ProjectCR", "symbol": "CR", "amount": "2M", "stage": "SeriesA", "investors": [{"name": "VC_B"}]}
            ]
        }

        mock_resp_cr_ido = MagicMock()
        mock_resp_cr_ido.json.return_value = {
            "data": [
                {"name": "TokenCR", "symbol": "TCR", "platform": "DAOMaker", "startDate": "2026-08-08"}
            ]
        }

        def mock_get_cr(url, params, headers, timeout):
            resp = MagicMock()
            if "/currencies/funding-rounds" in url:
                return mock_resp_cr_funding
            elif "/currencies/token-sales" in url:
                return mock_resp_cr_ido
            return resp

        self.mock_session_cr.get.side_effect = mock_get_cr

        # Mock OKBoost RSS response
        mock_resp_ok_rss = MagicMock()
        mock_resp_ok_rss.content = b"""<?xml version="1.0" encoding="UTF-8" ?>
        <rss version="2.0">
        <channel>
            <title>OKX Announcement</title>
            <item>
                <title>OKX Launchpool starts for Project E</title>
                <link>https://www.okx.com/help/1</link>
                <description>OKX Launchpool details here</description>
                <pubDate>Thu, 06 Aug 2026 10:00:00 GMT</pubDate>
            </item>
        </channel>
        </rss>"""
        self.mock_session_ok.get.return_value = mock_resp_ok_rss

        # Let's override today's date for deterministic matching in OKBoost RSS parse
        test_today = date(2026, 8, 6)

        with patch("datetime.date") as mock_date:
            mock_date.today.return_value = test_today
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            # Execute main.run_daily_job
            main.run_daily_job()

        # Check that expected API requests were triggered
        self.assertTrue(self.mock_session_rd.post.called)
        self.assertTrue(self.mock_session_cr.get.called)
        self.assertTrue(self.mock_session_ok.get.called)

        # Check notifier send_message was called with formatting matching the mocks
        mock_send_message.assert_called_once()
        report_text = mock_send_message.call_args[0][0]

        self.assertIn("ProjectA", report_text)
        self.assertIn("NewProjB", report_text)
        self.assertIn("EventC", report_text)
        self.assertIn("ProjectCR", report_text)
        self.assertIn("TokenCR", report_text)
        self.assertIn("OKX Launchpool starts for Project E", report_text)


if __name__ == "__main__":
    unittest.main()
