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

    def setUp(self):
        self.target_date = date(2026, 5, 10)

    @patch("requests.Session.request")
    def test_all_endpoints_integration(self, mock_request):
        # Setup mock responses for requests.Session.request
        def side_effect(method, url, *args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.ok = True

            # Check URLs to return correct mock data
            if "api.rootdata.com" in url:
                if "get_invest_list" in url:
                    mock_resp.json.return_value = {
                        "code": 200,
                        "data": {
                            "items": [{
                                "project_name": "Project A",
                                "amount": "$5M",
                                "round": "Seed",
                                "investors": ["VC A"],
                                "date": "2026-05-10",
                                "url": "https://url-a",
                                "description": "Desc A"
                            }]
                        }
                    }
                elif "get_pro_list" in url:
                    mock_resp.json.return_value = {
                        "code": 200,
                        "data": {
                            "items": [{
                                "project_name": "Project B",
                                "tags": ["DeFi"],
                                "description": "Desc B",
                                "add_time": "2026-05-10",
                                "url": "https://url-b"
                            }]
                        }
                    }
                elif "get_calendar_list" in url:
                    mock_resp.json.return_value = {
                        "code": 200,
                        "data": {
                            "items": [{
                                "project_name": "Project C",
                                "event_name": "Launch",
                                "date": "2026-05-10",
                                "url": "https://url-c",
                                "description": "Desc C"
                            }]
                        }
                    }
                elif "get_token_unlock" in url:
                    mock_resp.json.return_value = {
                        "code": 200,
                        "data": {
                            "items": [{
                                "project_name": "Project D",
                                "tge_date": "2026-05-10",
                                "symbol": "D",
                                "total_raise": "$1M",
                                "url": "https://url-d"
                            }]
                        }
                    }
                else:
                    mock_resp.json.return_value = {}

            elif "api.cryptorank.io" in url:
                if "funding-rounds" in url:
                    mock_resp.json.return_value = {
                        "data": [{
                            "name": "Project E",
                            "symbol": "E",
                            "amount": "$10M",
                            "stage": "Series A",
                            "investors": [{"name": "VC B"}],
                            "date": "2026-05-10",
                            "key": "e"
                        }]
                    }
                elif "token-sales" in url:
                    mock_resp.json.return_value = {
                        "data": [{
                            "name": "Project F",
                            "symbol": "F",
                            "platform": "Platform A",
                            "startDate": "2026-05-10",
                            "endDate": "2026-05-15",
                            "hardCap": "$2M",
                            "key": "f"
                        }]
                    }
                else:
                    mock_resp.json.return_value = {"data": []}

            elif "okx.com" in url:
                mock_resp.content = b"""<rss version="2.0">
                    <channel>
                        <item>
                            <title>OKX Jumpstart Launchpool Airdrop</title>
                            <link>https://okx-link</link>
                            <description><![CDATA[Join our OKX Jumpstart and Launchpool.]]></description>
                            <pubDate>Sun, 10 May 2026 10:00:00 GMT</pubDate>
                        </item>
                    </channel>
                </rss>"""

            elif "api.telegram.org" in url:
                mock_resp.json.return_value = {"ok": True}

            else:
                mock_resp.json.return_value = {}

            return mock_resp

        mock_request.side_effect = side_effect

        # 1. Test individual fetchers
        rd_funding = rootdata.get_daily_funding(self.target_date)
        self.assertEqual(len(rd_funding), 1)
        self.assertEqual(rd_funding[0]["name"], "Project A")

        rd_events = rootdata.get_project_events(self.target_date)
        self.assertEqual(len(rd_events), 1)
        self.assertEqual(rd_events[0]["name"], "Project C")

        rd_new = rootdata.get_new_projects(1)
        self.assertEqual(len(rd_new), 1)
        self.assertEqual(rd_new[0]["name"], "Project B")

        rd_tge = rootdata.get_upcoming_tge(7)
        self.assertEqual(len(rd_tge), 1)
        self.assertEqual(rd_tge[0]["name"], "Project D")

        cr_funding = cryptorank.get_daily_funding(self.target_date)
        self.assertEqual(len(cr_funding), 1)
        self.assertEqual(cr_funding[0]["name"], "Project E")

        cr_ido = cryptorank.get_upcoming_ido(7)
        self.assertEqual(len(cr_ido), 1)
        self.assertEqual(cr_ido[0]["name"], "Project F")

        okb = okboost.get_daily_okboost(self.target_date)
        self.assertEqual(len(okb), 1)
        self.assertEqual(okb[0]["title"], "OKX Jumpstart Launchpool Airdrop")

        # 2. Test overall job execution with the parallel processing
        with patch("main.date") as mock_date:
            mock_date.today.return_value = self.target_date
            main.run_daily_job()

        # Check that we actually requested the data.
        # Check that the Telegram sendMessage endpoint was hit.
        tg_sendMessage_called = False
        for call_args in mock_request.call_args_list:
            # call_args[0] or call_args[1] (args/kwargs)
            url_called = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("url", "")
            if "sendMessage" in url_called:
                tg_sendMessage_called = True
                break

        self.assertTrue(tg_sendMessage_called, "Telegram sendMessage endpoint should have been called")


if __name__ == "__main__":
    unittest.main()
