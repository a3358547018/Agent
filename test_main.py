import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import threading

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropDiscovery(unittest.TestCase):

    def test_get_session_thread_local(self):
        """测试 _get_session 返回线程局部独享的 requests.Session 实例"""
        # 获取当前主线程的 session
        session1 = rootdata._get_session()
        self.assertIsInstance(session1, rootdata.requests.Session)

        session2 = rootdata._get_session()
        self.assertIs(session1, session2)  # 同一线程多次获取应当是同一个

        # 在新线程中获取 session
        sessions_in_threads = []
        def get_sess():
            s = rootdata._get_session()
            sessions_in_threads.append(s)

        t = threading.Thread(target=get_sess)
        t.start()
        t.join()

        self.assertEqual(len(sessions_in_threads), 1)
        self.assertIsNot(session1, sessions_in_threads[0])  # 跨线程应该是不同的 session 实例

    @patch('rootdata._get_session')
    def test_rootdata_get_daily_funding(self, mock_get_session):
        """测试 rootdata 正常获取每日融资数据时的解析和返回"""
        mock_sess = MagicMock()
        mock_get_session.return_value = mock_sess

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {
                        "project_name": "Test Project",
                        "amount": "10M",
                        "round": "Seed",
                        "investors": ["A16Z", "Paradigm"],
                        "date": "2026-08-04",
                        "url": "https://www.rootdata.com/Projects/123",
                        "description": "Test Desc"
                    }
                ]
            }
        }
        mock_sess.post.return_value = mock_response

        res = rootdata.get_daily_funding(date(2026, 8, 4))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "Test Project")
        self.assertEqual(res[0]["amount"], "10M")
        self.assertEqual(res[0]["round"], "Seed")
        self.assertEqual(res[0]["investors"], ["A16Z", "Paradigm"])

    @patch('cryptorank._get_session')
    def test_cryptorank_get_daily_funding(self, mock_get_session):
        """测试 cryptorank 正常获取每日融资数据时的解析和返回"""
        mock_sess = MagicMock()
        mock_get_session.return_value = mock_sess

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "name": "CryptoRank Project",
                    "symbol": "CRP",
                    "amount": 5000000,
                    "stage": "Series A",
                    "investors": [{"name": "Binance Labs"}],
                    "date": "2026-08-04",
                    "key": "cryptorank-project"
                }
            ]
        }
        mock_sess.get.return_value = mock_response

        res = cryptorank.get_daily_funding(date(2026, 8, 4))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "CryptoRank Project")
        self.assertEqual(res[0]["symbol"], "CRP")
        self.assertEqual(res[0]["amount"], 5000000)
        self.assertEqual(res[0]["round"], "Series A")
        self.assertEqual(res[0]["investors"], ["Binance Labs"])

    @patch('okboost._get_session')
    def test_okboost_get_daily_okboost(self, mock_get_session):
        """测试 okboost RSS 抓取与关键词过滤和时间比较工作正常"""
        mock_sess = MagicMock()
        mock_get_session.return_value = mock_sess

        mock_response = MagicMock()
        # RSS XML 模拟内容，pubDate 转为 2026-08-04 (Tue, 04 Aug 2026 12:00:00 GMT)
        xml_content = b"""<rss version="2.0">
            <channel>
                <item>
                    <title>OKX will launch launchpool for TestToken</title>
                    <link>https://www.okx.com/help/123</link>
                    <description>Stake OKB to farm TestToken</description>
                    <pubDate>Tue, 04 Aug 2026 12:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""
        mock_response.content = xml_content
        mock_sess.get.return_value = mock_response

        res = okboost.get_daily_okboost(date(2026, 8, 4))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "OKX will launch launchpool for TestToken")
        self.assertEqual(res[0]["url"], "https://www.okx.com/help/123")

    @patch('main.rootdata')
    @patch('main.cryptorank')
    @patch('main.okboost')
    @patch('main.send_message')
    def test_run_daily_job_concurrent(self, mock_send_message, mock_okboost, mock_cryptorank, mock_rootdata):
        """测试 run_daily_job 并行执行所有 7 个数据抓取任务并触发 send_message"""
        mock_rootdata.get_daily_funding.return_value = [{"name": "RD Funding"}]
        mock_rootdata.get_project_events.return_value = [{"name": "RD Event"}]
        mock_rootdata.get_new_projects.return_value = [{"name": "RD New Proj"}]
        mock_rootdata.get_upcoming_tge.return_value = [{"name": "RD TGE"}]
        mock_cryptorank.get_daily_funding.return_value = [{"name": "CR Funding"}]
        mock_cryptorank.get_upcoming_ido.return_value = [{"name": "CR IDO"}]
        mock_okboost.get_daily_okboost.return_value = [{"title": "OKB"}]

        main.run_daily_job()

        # 验证所有 7 个抓取 API 被触发
        mock_rootdata.get_daily_funding.assert_called_once()
        mock_rootdata.get_project_events.assert_called_once()
        mock_rootdata.get_new_projects.assert_called_once_with(1)
        mock_rootdata.get_upcoming_tge.assert_called_once_with(7)
        mock_cryptorank.get_daily_funding.assert_called_once()
        mock_cryptorank.get_upcoming_ido.assert_called_once_with(7)
        mock_okboost.get_daily_okboost.assert_called_once()

        # 验证 send_message 被调用
        mock_send_message.assert_called_once()
        # 验证推送的内容包含我们 mock 出来的那些内容
        report_text = mock_send_message.call_args[0][0]
        self.assertIn("RD Funding", report_text)
        self.assertIn("RD Event", report_text)
        self.assertIn("RD New Proj", report_text)
        self.assertIn("RD TGE", report_text)
        self.assertIn("CR Funding", report_text)
        self.assertIn("CR IDO", report_text)
        self.assertIn("OKB", report_text)


if __name__ == '__main__':
    unittest.main()
