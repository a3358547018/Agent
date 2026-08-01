import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import threading

import main
import rootdata
import cryptorank
import okboost
import notifier

class TestAirdropAgent(unittest.TestCase):

    def test_extract_items(self):
        """测试 rootdata 中的 _extract_items 辅助函数。"""
        # 1. 列表直接返回
        self.assertEqual(rootdata._extract_items([1, 2, 3]), [1, 2, 3])
        # 2. 字典包含 items
        self.assertEqual(rootdata._extract_items({"items": [4, 5]}), [4, 5])
        # 3. 字典包含 list
        self.assertEqual(rootdata._extract_items({"list": [6, 7]}), [6, 7])
        # 4. 空值或其它类型
        self.assertEqual(rootdata._extract_items(None), [])
        self.assertEqual(rootdata._extract_items("not a list"), [])

    def test_thread_local_session(self):
        """测试各模块的 _get_session 为线程局部，且能正确提供 Session 实例。"""
        # 测试在主线程中获取 Session 实例
        rd_session = rootdata._get_session()
        self.assertIsNotNone(rd_session)

        cr_session = cryptorank._get_session()
        self.assertIsNotNone(cr_session)

        ok_session = okboost._get_session()
        self.assertIsNotNone(ok_session)

        nt_session = notifier._get_session()
        self.assertIsNotNone(nt_session)

        # 验证不同线程获取到不同的 session 实例
        sessions = {}
        def worker(name):
            sessions[name] = rootdata._get_session()

        t1 = threading.Thread(target=worker, args=("t1",))
        t2 = threading.Thread(target=worker, args=("t2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertNotEqual(sessions["t1"], sessions["t2"])

    @patch("rootdata.get_daily_funding")
    @patch("rootdata.get_project_events")
    @patch("rootdata.get_new_projects")
    @patch("rootdata.get_upcoming_tge")
    @patch("cryptorank.get_daily_funding")
    @patch("cryptorank.get_upcoming_ido")
    @patch("okboost.get_daily_okboost")
    @patch("main.send_message")
    def test_run_daily_job_orchestration(
        self,
        mock_send,
        mock_okboost,
        mock_cr_ido,
        mock_cr_funding,
        mock_rd_tge,
        mock_rd_new,
        mock_rd_events,
        mock_rd_funding
    ):
        """测试 run_daily_job 的并行抓取、报告格式化和推送流程。"""
        # 设置 Mock 的返回值
        mock_rd_funding.return_value = [{"name": "RD Proj", "amount": "1M", "round": "Seed", "investors": ["VC A"], "url": "https://rd"}]
        mock_rd_events.return_value = [{"name": "RD Event Proj", "event": "Mainnet Launch", "date": "2026-08-01", "url": "https://rde"}]
        mock_rd_new.return_value = [{"name": "RD New Proj", "category": ["DeFi"], "desc": "Great DeFi proj", "url": "https://rdn"}]
        mock_rd_tge.return_value = [{"name": "RD TGE Proj", "tge_date": "2026-08-05", "token": "RDT", "url": "https://rdt"}]
        mock_cr_funding.return_value = [{"name": "CR Proj", "symbol": "CRP", "amount": "2M", "round": "Series A", "investors": ["VC B"], "url": "https://cr"}]
        mock_cr_ido.return_value = [{"name": "CR IDO Proj", "symbol": "CRI", "platform": "DAOMaker", "start_date": "2026-08-03", "url": "https://cri"}]
        mock_okboost.return_value = [{"title": "OKX Listing", "desc": "OKX will list some token", "url": "https://okx", "date": "2026-08-01"}]

        # 执行任务
        main.run_daily_job()

        # 验证抓取函数是否都被调用
        mock_rd_funding.assert_called_once()
        mock_rd_events.assert_called_once()
        mock_rd_new.assert_called_once()
        mock_rd_tge.assert_called_once()
        mock_cr_funding.assert_called_once()
        mock_cr_ido.assert_called_once()
        mock_okboost.assert_called_once()

        # 验证 send_message 被调用，且消息格式包含 mock 里的各种标志性关键字
        mock_send.assert_called_once()
        sent_message = mock_send.call_args[0][0]
        self.assertIn("RD Proj", sent_message)
        self.assertIn("RD Event Proj", sent_message)
        self.assertIn("RD New Proj", sent_message)
        self.assertIn("RD TGE Proj", sent_message)
        self.assertIn("CR Proj", sent_message)
        self.assertIn("CR IDO Proj", sent_message)
        self.assertIn("OKX Listing", sent_message)

    @patch("rootdata._get_session")
    def test_rootdata_post_api(self, mock_get_session):
        """测试 rootdata 模块的数据请求与处理，验证安全提取。"""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        # 模拟 POST 请求返回成功且数据为字典
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {
                        "project_name": "TestRD",
                        "amount": "$5M",
                        "round": "Seed",
                        "investors": ["Lead VC"],
                        "url": "http://testrd",
                        "description": "desc"
                    }
                ]
            }
        }
        mock_session.post.return_value = mock_response

        # 调用方法
        res = rootdata.get_daily_funding()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "TestRD")
        self.assertEqual(res[0]["amount"], "$5M")

    @patch("cryptorank._get_session")
    def test_cryptorank_get_api(self, mock_get_session):
        """测试 cryptorank 模块的 GET 数据请求与处理。"""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "name": "TestCR",
                    "symbol": "TCR",
                    "amount": 1000000,
                    "stage": "Seed",
                    "investors": [{"name": "VC1"}],
                    "key": "testcr"
                }
            ]
        }
        mock_session.get.return_value = mock_response

        res = cryptorank.get_daily_funding()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "TestCR")
        self.assertEqual(res[0]["symbol"], "TCR")

if __name__ == "__main__":
    unittest.main()
