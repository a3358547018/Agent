import unittest
from unittest.mock import MagicMock, patch
import threading
from datetime import date, datetime, timezone
import requests

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropAgent(unittest.TestCase):

    def test_thread_local_sessions(self):
        """测试 4 个模块的 _get_session 均返回 requests.Session，并且在不同线程中是独立的。"""
        modules = [rootdata, cryptorank, okboost, notifier]
        for mod in modules:
            self.assertTrue(hasattr(mod, "_get_session"))
            session = mod._get_session()
            self.assertIsInstance(session, requests.Session)

            # 在另一个线程中调用，应该返回不同的 Session 实例
            other_session = []
            def get_other():
                other_session.append(mod._get_session())
            t = threading.Thread(target=get_other)
            t.start()
            t.join()

            self.assertNotEqual(id(session), id(other_session[0]))

    @patch("rootdata._get_session")
    def test_rootdata_fetching(self, mock_get_session):
        """测试 RootData 数据抓取与解析逻辑。"""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        # 1. get_daily_funding
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 200,
            "data": [
                {
                    "project_name": "Test Project",
                    "amount": "$10M",
                    "round": "Series A",
                    "investors": ["Investor A", "Investor B"],
                    "date": "2026-07-31",
                    "url": "https://rootdata.com/test",
                    "description": "Test Desc"
                }
            ]
        }
        mock_session.post.return_value = mock_response

        funding = rootdata.get_daily_funding(date(2026, 7, 31))
        self.assertEqual(len(funding), 1)
        self.assertEqual(funding[0]["name"], "Test Project")
        self.assertEqual(funding[0]["amount"], "$10M")
        self.assertEqual(funding[0]["round"], "Series A")
        self.assertEqual(funding[0]["investors"], ["Investor A", "Investor B"])

        # 2. get_new_projects
        mock_response.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {
                        "project_name": "New Project",
                        "tags": ["DeFi", "L2"],
                        "description": "Short description",
                        "add_time": "2026-07-31",
                        "url": "https://rootdata.com/new"
                    }
                ]
            }
        }
        new_projects = rootdata.get_new_projects(days=1)
        self.assertEqual(len(new_projects), 1)
        self.assertEqual(new_projects[0]["name"], "New Project")
        self.assertEqual(new_projects[0]["category"], ["DeFi", "L2"])

    @patch("cryptorank._get_session")
    def test_cryptorank_fetching(self, mock_get_session):
        """测试 CryptoRank V2 接口的数据解析。"""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "name": "Crypto Project",
                    "symbol": "CR",
                    "amount": "$5M",
                    "stage": "Seed",
                    "investors": [{"name": "VC 1"}, {"name": "VC 2"}],
                    "date": "2026-07-31",
                    "key": "crypto-project"
                }
            ]
        }
        mock_session.get.return_value = mock_response

        funding = cryptorank.get_daily_funding(date(2026, 7, 31))
        self.assertEqual(len(funding), 1)
        self.assertEqual(funding[0]["name"], "Crypto Project")
        self.assertEqual(funding[0]["symbol"], "CR")
        self.assertEqual(funding[0]["investors"], ["VC 1", "VC 2"])

    @patch("okboost._get_session")
    def test_okboost_fetching(self, mock_get_session):
        """测试 OKBoost 抓取 RSS 和过滤逻辑。"""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        xml_data = b"""<?xml version="1.0" encoding="UTF-8" ?>
        <rss version="2.0">
        <channel>
            <title>OKX Help Center</title>
            <item>
                <title>OKX to launch jumpstart for new token</title>
                <link>https://www.okx.com/help/123</link>
                <description>&lt;p&gt;This is a description about jumpstart. See more.&lt;/p&gt;</description>
                <pubDate>Fri, 31 Jul 2026 10:00:00 GMT</pubDate>
            </item>
            <item>
                <title>Unrelated Announcement</title>
                <link>https://www.okx.com/help/456</link>
                <description>&lt;p&gt;Not containing any keywords.&lt;/p&gt;</description>
                <pubDate>Fri, 31 Jul 2026 11:00:00 GMT</pubDate>
            </item>
        </channel>
        </rss>"""

        mock_response = MagicMock()
        mock_response.content = xml_data
        mock_session.get.return_value = mock_response

        # 指定日期为 2026-07-31
        target = date(2026, 7, 31)
        res = okboost.get_daily_okboost(target)

        # 应该只命中带有 "jumpstart" 的那个条目
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "OKX to launch jumpstart for new token")
        self.assertIn("jumpstart", res[0]["desc"])

    @patch("notifier._get_session")
    def test_notifier_sending_and_formatting(self, mock_get_session):
        """测试 Telegram 消息格式化与自动分段发送。"""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_response = MagicMock()
        mock_response.ok = True
        mock_session.post.return_value = mock_response

        # 测试 html.escape
        escaped_report = notifier.fmt_daily_report(
            rd_funding=[{"name": "<b>Bold</b> & Project", "amount": "$10M", "round": "Seed", "investors": ["A < B"], "url": ""}],
            rd_events=[],
            rd_new_proj=[],
            rd_tge=[],
            cr_funding=[],
            cr_ido=[],
            okboost=[],
            report_date="2026-07-31"
        )
        self.assertIn("&lt;b&gt;Bold&lt;/b&gt; &amp; Project", escaped_report)
        self.assertIn("A &lt; B", escaped_report)

        # 测试超长消息自动切分
        long_text = "Line\n\n" * 1000  # 远超 4000 字符限制
        notifier.send_message(long_text)
        self.assertTrue(mock_session.post.call_count > 1)

    @patch("rootdata.get_daily_funding")
    @patch("rootdata.get_project_events")
    @patch("rootdata.get_new_projects")
    @patch("rootdata.get_upcoming_tge")
    @patch("cryptorank.get_daily_funding")
    @patch("cryptorank.get_upcoming_ido")
    @patch("okboost.get_daily_okboost")
    @patch("main.send_message")
    def test_parallel_scheduling(self, mock_send, mock_ok, mock_cr_ido, mock_cr_fund, mock_rd_tge, mock_rd_new, mock_rd_ev, mock_rd_fund):
        """验证 main.py 并行调度框架能正确汇集结果并推送。"""
        mock_rd_fund.return_value = [{"name": "RD Fund", "amount": "$1M", "round": "Seed", "investors": ["A"], "url": ""}]
        mock_rd_ev.return_value = []
        mock_rd_new.return_value = []
        mock_rd_tge.return_value = []
        mock_cr_fund.return_value = []
        mock_cr_ido.return_value = []
        mock_ok.return_value = []

        main.run_daily_job()

        # 确保所有 mock 都被调用了
        mock_rd_fund.assert_called_once()
        mock_rd_ev.assert_called_once()
        mock_rd_new.assert_called_once()
        mock_rd_tge.assert_called_once()
        mock_cr_fund.assert_called_once()
        mock_cr_ido.assert_called_once()
        mock_ok.assert_called_once()
        mock_send.assert_called_once()

        # 验证发出的消息包含 mock 数据
        report_text = mock_send.call_args[0][0]
        self.assertIn("RD Fund", report_text)


if __name__ == "__main__":
    unittest.main()
