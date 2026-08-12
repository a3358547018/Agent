import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import main


class TestAirdropAgent(unittest.TestCase):

    @patch("main.send_message")
    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("main.date")
    @patch("okboost.date")
    def test_run_daily_job_success(
        self,
        mock_okboost_date,
        mock_main_date,
        mock_okboost_session_get,
        mock_cryptorank_session_get,
        mock_rootdata_session_get,
        mock_send_message,
    ):
        # Mock date to be deterministic
        fixed_date = date(2023, 10, 24)
        mock_main_date.today.return_value = fixed_date
        mock_okboost_date.today.return_value = fixed_date

        # Mock sessions and their HTTP calls
        mock_rd_sess = MagicMock()
        mock_rootdata_session_get.return_value = mock_rd_sess

        mock_cr_sess = MagicMock()
        mock_cryptorank_session_get.return_value = mock_cr_sess

        mock_ok_sess = MagicMock()
        mock_okboost_session_get.return_value = mock_ok_sess

        # Mock RootData responses
        # /get_invest_list, /get_calendar_list, /get_pro_list, /get_token_unlock
        def rd_post_side_effect(url, json, headers, timeout):
            endpoint = url.split("/open")[-1]
            if endpoint == "/get_invest_list":
                return MagicMock(ok=True, json=lambda: {"result": True, "data": {"items": [
                    {"project_name": "Project A", "amount": "$10M", "round": "Series A", "investors": ["Investor 1"], "id": 1}
                ]}})
            elif endpoint == "/get_calendar_list":
                return MagicMock(ok=True, json=lambda: {"result": True, "data": {"items": [
                    {"project_name": "Project B", "event_name": "Mainnet", "date": "2023-10-24"}
                ]}})
            elif endpoint == "/get_pro_list":
                return MagicMock(ok=True, json=lambda: {"result": True, "data": {"items": [
                    {"project_name": "Project C", "tags": ["DeFi"], "description": "A cool defi project", "id": 3}
                ]}})
            elif endpoint == "/get_token_unlock":
                return MagicMock(ok=True, json=lambda: {"result": True, "data": {"items": [
                    {"project_name": "Project D", "symbol": "PROJ", "tge_date": "2023-10-31", "raise_amount": "1M", "id": 4}
                ]}})
            return MagicMock(ok=True, json=lambda: {"result": True, "data": {}})

        mock_rd_sess.post.side_effect = rd_post_side_effect

        # Mock CryptoRank responses
        # /currencies/funding-rounds, /currencies/token-sales
        def cr_get_side_effect(url, params, headers, timeout):
            endpoint = url.split("/v2")[-1]
            if endpoint == "/currencies/funding-rounds":
                return MagicMock(ok=True, json=lambda: {"data": [
                    {"name": "CR Project A", "symbol": "CRA", "amount": "$5M", "stage": "Seed", "investors": [{"name": "VC A"}]}
                ]})
            elif endpoint == "/currencies/token-sales":
                return MagicMock(ok=True, json=lambda: {"data": [
                    {"name": "CR Project B", "symbol": "CRB", "platform": "DAOMaker", "startDate": "2023-10-25"}
                ]})
            return MagicMock(ok=True, json=lambda: {"data": []})

        mock_cr_sess.get.side_effect = cr_get_side_effect

        # Mock OKBoost RSS response
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>OKX list new coin boost</title>
                    <link>https://okx.com/notice</link>
                    <description>&lt;p&gt;OKX Launchpool listing new boost coin&lt;/p&gt;</description>
                    <pubDate>Tue, 24 Oct 2023 10:00:00 GMT</pubDate>
                </item>
                <item>
                    <title>OKX regular notice</title>
                    <link>https://okx.com/regular</link>
                    <description>Regular notice details</description>
                    <pubDate>Mon, 23 Oct 2023 10:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>
        """
        mock_ok_sess.get.return_value = MagicMock(ok=True, content=rss_xml.encode("utf-8"))

        # Run the daily job
        main.run_daily_job()

        # Assertions
        mock_send_message.assert_called_once()
        sent_report = mock_send_message.call_args[0][0]
        self.assertIn("空投项目日报 · 2023-10-24", sent_report)
        self.assertIn("Project A", sent_report)
        self.assertIn("Project B", sent_report)
        self.assertIn("Project C", sent_report)
        self.assertIn("Project D", sent_report)
        self.assertIn("CR Project A", sent_report)
        self.assertIn("CR Project B", sent_report)
        self.assertIn("OKX list new coin boost", sent_report)


if __name__ == "__main__":
    unittest.main()
