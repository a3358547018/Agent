import unittest
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timezone
import sys

# Ensure current directory is in path
sys.path.append('.')

import rootdata
import cryptorank
import okboost
import notifier
import main

class TestAirdropDiscovery(unittest.TestCase):

    @patch('rootdata._post')
    def test_rootdata_parsers(self, mock_post):
        # 1. Test get_daily_funding
        mock_post.return_value = {
            "items": [
                {
                    "project_name": "Test Project",
                    "amount": "$5M",
                    "round": "Seed",
                    "investors": ["VC A", "VC B"],
                    "date": "2023-10-10",
                    "url": "https://test.com",
                    "description": "Desc"
                }
            ]
        }
        res = rootdata.get_daily_funding(date(2023, 10, 10))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "Test Project")
        self.assertEqual(res[0]["amount"], "$5M")

        # 2. Test get_new_projects
        mock_post.return_value = {
            "items": [
                {
                    "project_name": "New Proj",
                    "tags": ["DeFi"],
                    "description": "Desc",
                    "add_time": "2023-10-10",
                    "url": "https://test.com"
                }
            ]
        }
        res = rootdata.get_new_projects(days=1)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "New Proj")

        # 3. Test get_project_events
        mock_post.return_value = {
            "items": [
                {
                    "project_name": "Event Proj",
                    "event_name": "Mainnet Launch",
                    "date": "2023-10-10",
                    "url": "https://test.com",
                    "description": "Desc"
                }
            ]
        }
        res = rootdata.get_project_events(date(2023, 10, 10))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["event"], "Mainnet Launch")

        # 4. Test get_upcoming_tge
        mock_post.return_value = {
            "items": [
                {
                    "project_name": "TGE Proj",
                    "tge_date": "2023-10-10",
                    "symbol": "TEST",
                    "total_raise": "$2M",
                    "url": "https://test.com"
                }
            ]
        }
        res = rootdata.get_upcoming_tge(days_ahead=7)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["token"], "TEST")

    @patch('cryptorank._get')
    def test_cryptorank_parsers(self, mock_get):
        # 1. Test get_daily_funding
        mock_get.return_value = {
            "data": [
                {
                    "name": "CR Proj",
                    "symbol": "CRP",
                    "amount": "$3M",
                    "stage": "Series A",
                    "investors": [{"name": "VC C"}],
                    "date": "2023-10-10",
                    "key": "cr-proj"
                }
            ]
        }
        res = cryptorank.get_daily_funding(date(2023, 10, 10))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "CR Proj")
        self.assertEqual(res[0]["investors"], ["VC C"])

        # 2. Test get_upcoming_ido
        mock_get.return_value = {
            "data": [
                {
                    "name": "CR IDO Proj",
                    "symbol": "CRID",
                    "platform": "DAO Maker",
                    "startDate": "2023-10-10",
                    "endDate": "2023-10-12",
                    "hardCap": "$1M",
                    "key": "cr-ido"
                }
            ]
        }
        res = cryptorank.get_upcoming_ido(days_ahead=7)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["platform"], "DAO Maker")

    @patch('okboost._fetch_rss')
    def test_okboost_parser(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "title": "OKX Jumpstart Launchpool is live!",
                "link": "https://okx.com/news/1",
                "desc": "Join the new Jumpstart to get tokens",
                "pub_dt": datetime(2023, 10, 10, tzinfo=timezone.utc)
            },
            {
                "title": "Unrelated news title",
                "link": "https://okx.com/news/2",
                "desc": "This is random and has no match keywords",
                "pub_dt": datetime(2023, 10, 10, tzinfo=timezone.utc)
            }
        ]
        res = okboost.get_daily_okboost(date(2023, 10, 10))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "OKX Jumpstart Launchpool is live!")

    def test_message_formatter(self):
        rd_funding = [{"name": "P1", "round": "Seed", "amount": "$1M", "investors": ["VC A"], "url": "https://p1.com"}]
        rd_events = [{"name": "P1", "event": "Launch", "date": "2023-10-10", "url": "https://p1.com"}]
        rd_new_proj = [{"name": "P2", "category": ["DeFi"], "desc": "Desc P2", "url": "https://p2.com"}]
        rd_tge = [{"name": "P3", "tge_date": "2023-10-15", "token": "P3T", "url": "https://p3.com"}]
        cr_funding = [{"name": "P4", "symbol": "P4T", "round": "Seed", "amount": "$2M", "investors": ["VC B"], "url": "https://p4.com"}]
        cr_ido = [{"name": "P5", "start_date": "2023-10-16", "symbol": "P5T", "url": "https://p5.com"}]
        okboost_data = [{"title": "OKX Event", "desc": "OKX Event Desc", "url": "https://okx.com"}]

        report = notifier.fmt_daily_report(
            rd_funding=rd_funding,
            rd_events=rd_events,
            rd_new_proj=rd_new_proj,
            rd_tge=rd_tge,
            cr_funding=cr_funding,
            cr_ido=cr_ido,
            okboost=okboost_data,
            report_date="2023-10-10"
        )
        self.assertIn("空投项目日报", report)
        self.assertIn("P1", report)
        self.assertIn("P2", report)
        self.assertIn("P3", report)
        self.assertIn("P4", report)
        self.assertIn("P5", report)
        self.assertIn("OKX Event", report)

    @patch('main.send_message')
    @patch('rootdata.get_daily_funding')
    @patch('rootdata.get_project_events')
    @patch('rootdata.get_new_projects')
    @patch('rootdata.get_upcoming_tge')
    @patch('cryptorank.get_daily_funding')
    @patch('cryptorank.get_upcoming_ido')
    @patch('okboost.get_daily_okboost')
    def test_run_daily_job_orchestration(self, mock_okboost, mock_cr_ido, mock_cr_funding,
                                         mock_rd_tge, mock_rd_new, mock_rd_events, mock_rd_funding,
                                         mock_send_msg):
        # Set return values
        mock_rd_funding.return_value = []
        mock_rd_events.return_value = []
        mock_rd_new.return_value = []
        mock_rd_tge.return_value = []
        mock_cr_funding.return_value = []
        mock_cr_ido.return_value = []
        mock_okboost.return_value = []

        main.run_daily_job()

        # Check all APIs were fetched
        mock_rd_funding.assert_called_once()
        mock_rd_events.assert_called_once()
        mock_rd_new.assert_called_once()
        mock_rd_tge.assert_called_once()
        mock_cr_funding.assert_called_once()
        mock_cr_ido.assert_called_once()
        mock_okboost.assert_called_once()
        mock_send_msg.assert_called_once()

if __name__ == '__main__':
    unittest.main()
