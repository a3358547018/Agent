import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropAgent(unittest.TestCase):

    @patch('requests.Session.request')
    def test_rootdata_get_daily_funding(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": {
                "items": [
                    {
                        "project_name": "Test Project",
                        "amount": "1000000",
                        "financing_round": "Seed",
                        "investors": ["VC 1", "VC 2"],
                        "date": "2026-05-10",
                        "url": "https://rootdata.com/test",
                        "description": "A cool test project"
                    }
                ]
            }
        }
        mock_request.return_value = mock_response

        res = rootdata.get_daily_funding(date(2026, 5, 10))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "Test Project")
        self.assertEqual(res[0]["amount"], "1000000")

    @patch('requests.Session.request')
    def test_rootdata_get_new_projects(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": {
                "items": [
                    {
                        "project_name": "New Proj",
                        "tags": ["DeFi"],
                        "description": "new project desc",
                        "add_time": "2026-05-10",
                        "url": "https://rootdata.com/new"
                    }
                ]
            }
        }
        mock_request.return_value = mock_response

        res = rootdata.get_new_projects(1)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "New Proj")

    @patch('requests.Session.request')
    def test_cryptorank_get_daily_funding(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "name": "CryptoRank Proj",
                    "symbol": "CRP",
                    "amount": "500000",
                    "stage": "A",
                    "investors": [{"name": "VC A"}],
                    "date": "2026-05-10",
                    "key": "cr-proj"
                }
            ]
        }
        mock_request.return_value = mock_response

        res = cryptorank.get_daily_funding(date(2026, 5, 10))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "CryptoRank Proj")

    @patch('requests.Session.request')
    def test_okboost_get_daily_okboost(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""<rss version="2.0">
            <channel>
                <item>
                    <title>OKX Launchpool for Token X</title>
                    <link>https://okx.com/announce1</link>
                    <description>Great news! OKX Launchpool for Token X is starting.</description>
                    <pubDate>Sun, 10 May 2026 10:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""
        mock_request.return_value = mock_response

        res = okboost.get_daily_okboost(date(2026, 5, 10))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "OKX Launchpool for Token X")

    @patch('requests.Session.request')
    def test_notifier_send_message(self, mock_request):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_request.return_value = mock_response

        notifier.send_message("Hello from test bot!")
        self.assertTrue(mock_request.called)

    @patch('main.send_message')
    @patch('main.fmt_daily_report')
    @patch('rootdata.get_daily_funding')
    @patch('rootdata.get_project_events')
    @patch('rootdata.get_new_projects')
    @patch('rootdata.get_upcoming_tge')
    @patch('cryptorank.get_daily_funding')
    @patch('cryptorank.get_upcoming_ido')
    @patch('okboost.get_daily_okboost')
    def test_run_daily_job_parallelism(self, mock_ok, mock_cr_ido, mock_cr_fund, mock_rd_tge, mock_rd_new, mock_rd_evt, mock_rd_fund, mock_fmt, mock_send):
        mock_rd_fund.return_value = []
        mock_rd_evt.return_value = []
        mock_rd_new.return_value = []
        mock_rd_tge.return_value = []
        mock_cr_fund.return_value = []
        mock_cr_ido.return_value = []
        mock_ok.return_value = []

        main.run_daily_job()

        self.assertTrue(mock_rd_fund.called)
        self.assertTrue(mock_rd_evt.called)
        self.assertTrue(mock_rd_new.called)
        self.assertTrue(mock_rd_tge.called)
        self.assertTrue(mock_cr_fund.called)
        self.assertTrue(mock_cr_ido.called)
        self.assertTrue(mock_ok.called)
        self.assertTrue(mock_fmt.called)
        self.assertTrue(mock_send.called)
