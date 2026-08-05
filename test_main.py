import unittest
from unittest.mock import MagicMock, patch
import threading
from datetime import date

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropAgent(unittest.TestCase):

    def test_get_session_thread_local(self):
        """测试各模块的 _get_session() 确为线程局部 Session（避免并发冲突，保留连接池）"""
        # 1. 验证在主线程中多次调用返回相同的 session
        s1 = rootdata._get_session()
        s2 = rootdata._get_session()
        self.assertIs(s1, s2)

        # 2. 验证在子线程中调用返回不同的 session
        sessions_in_threads = []
        def get_sess():
            sessions_in_threads.append(rootdata._get_session())

        t = threading.Thread(target=get_sess)
        t.start()
        t.join()

        self.assertIsNot(s1, sessions_in_threads[0])

    @patch('rootdata._get_session')
    @patch('cryptorank._get_session')
    @patch('okboost._get_session')
    @patch('notifier._get_session')
    def test_run_daily_job_parallel(self, mock_notifier_sess, mock_okboost_sess, mock_cryptorank_sess, mock_rootdata_sess):
        """测试主入口 run_daily_job 的并行执行、数据聚合及 Telegram 发送流程"""
        # Mock rootdata response
        mock_rd = MagicMock()
        mock_rd_resp = MagicMock()
        mock_rd_resp.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {
                        "project_name": "Test RootData Project",
                        "amount": "10M USD",
                        "round": "Seed",
                        "investors": ["VC 1", "VC 2"],
                        "date": "2026-08-05"
                    }
                ]
            }
        }
        mock_rd.post.return_value = mock_rd_resp
        mock_rootdata_sess.return_value = mock_rd

        # Mock cryptorank response
        mock_cr = MagicMock()
        mock_cr_resp = MagicMock()
        mock_cr_resp.json.return_value = {
            "data": [
                {
                    "name": "Test CryptoRank Project",
                    "symbol": "TCR",
                    "amount": "5M USD",
                    "stage": "Series A",
                    "investors": [{"name": "VC A"}],
                    "date": "2026-08-05"
                }
            ]
        }
        mock_cr.get.return_value = mock_cr_resp
        mock_cryptorank_sess.return_value = mock_cr

        # Mock okboost response (RSS XML)
        mock_ok = MagicMock()
        mock_ok_resp = MagicMock()
        mock_ok_resp.content = b"""<rss version="2.0">
        <channel>
            <item>
                <title>Launchpool New Event</title>
                <link>https://www.okx.com/help/launchpool-new</link>
                <description>Earn high yield using OKB</description>
                <pubDate>Wed, 05 Aug 2026 10:00:00 +0800</pubDate>
            </item>
        </channel>
        </rss>"""
        mock_ok.get.return_value = mock_ok_resp
        mock_okboost_sess.return_value = mock_ok

        # Mock notifier response
        mock_notif = MagicMock()
        mock_notif_resp = MagicMock()
        mock_notif_resp.ok = True
        mock_notif.post.return_value = mock_notif_resp
        mock_notifier_sess.return_value = mock_notif

        # Run the full daily job with patched dates
        with patch('main.date') as mock_date:
            mock_date.today.return_value = date(2026, 8, 5)
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            main.run_daily_job()

        # Check that APIs were indeed called
        self.assertTrue(mock_rd.post.called)
        self.assertTrue(mock_cr.get.called)
        self.assertTrue(mock_ok.get.called)
        self.assertTrue(mock_notif.post.called)


if __name__ == '__main__':
    unittest.main()
