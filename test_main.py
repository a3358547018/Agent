import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import main

class TestDailyJob(unittest.TestCase):

    @patch("main.date")
    @patch("rootdata.get_daily_funding")
    @patch("rootdata.get_project_events")
    @patch("rootdata.get_new_projects")
    @patch("rootdata.get_upcoming_tge")
    @patch("cryptorank.get_daily_funding")
    @patch("cryptorank.get_upcoming_ido")
    @patch("okboost.get_daily_okboost")
    @patch("main.send_message")
    def test_run_daily_job_success(
        self,
        mock_send_message,
        mock_get_daily_okboost,
        mock_get_upcoming_ido,
        mock_cr_get_daily_funding,
        mock_get_upcoming_tge,
        mock_get_new_projects,
        mock_get_project_events,
        mock_rd_get_daily_funding,
        mock_date
    ):
        # Configure mock date to be static
        mock_date.today.return_value = date(2026, 8, 11)

        # Configure mocked return values
        mock_rd_get_daily_funding.return_value = [{"name": "RD Project", "amount": "1M", "round": "Seed", "investors": ["A"], "url": "url1"}]
        mock_get_project_events.return_value = [{"name": "RD Event", "event": "Launch", "date": "2026-08-11", "url": "url2"}]
        mock_get_new_projects.return_value = [{"name": "RD New", "category": ["DeFi"], "desc": "Cool", "url": "url3"}]
        mock_get_upcoming_tge.return_value = [{"name": "RD TGE", "tge_date": "2026-08-15", "token": "RDT", "url": "url4"}]
        mock_cr_get_daily_funding.return_value = [{"name": "CR Project", "symbol": "CRP", "amount": "2M", "round": "Series A", "investors": ["B"], "url": "url5"}]
        mock_get_upcoming_ido.return_value = [{"name": "CR IDO", "symbol": "CRI", "platform": "DAOMaker", "start_date": "2026-08-12", "url": "url6"}]
        mock_get_daily_okboost.return_value = [{"title": "OKX Campaign", "desc": "Join", "url": "url7", "date": "2026-08-11"}]

        # Run the daily job which runs them in parallel worker threads
        main.run_daily_job()

        # Check that send_message was called with formatting results
        mock_send_message.assert_called_once()
        sent_report = mock_send_message.call_args[0][0]
        self.assertIn("RD Project", sent_report)
        self.assertIn("RD Event", sent_report)
        self.assertIn("RD New", sent_report)
        self.assertIn("RD TGE", sent_report)
        self.assertIn("CR Project", sent_report)
        self.assertIn("CR IDO", sent_report)
        self.assertIn("OKX Campaign", sent_report)

    @patch("main.date")
    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("notifier._get_session")
    @patch("main.send_message")
    def test_run_daily_job_failures_resilient(
        self,
        mock_send_message,
        mock_notifier_session,
        mock_okboost_session,
        mock_cryptorank_session,
        mock_rootdata_session,
        mock_date
    ):
        mock_date.today.return_value = date(2026, 8, 11)

        # Set sessions to raise exceptions to simulate network issues
        mock_rd_sess = MagicMock()
        mock_rd_sess.post.side_effect = Exception("RootData network failure")
        mock_rootdata_session.return_value = mock_rd_sess

        mock_cr_sess = MagicMock()
        mock_cr_sess.get.side_effect = Exception("CryptoRank network failure")
        mock_cryptorank_session.return_value = mock_cr_sess

        mock_ok_sess = MagicMock()
        mock_ok_sess.get.side_effect = Exception("OKX network failure")
        mock_okboost_session.return_value = mock_ok_sess

        # The execution should not crash and still send an empty report gracefully
        main.run_daily_job()
        mock_send_message.assert_called_once()
        sent_report = mock_send_message.call_args[0][0]
        self.assertIn("今日暂无项目动态", sent_report)
        self.assertIn("今日暂无 RootData 融资数据", sent_report)
        self.assertIn("今日暂无 CryptoRank 融资数据", sent_report)

if __name__ == "__main__":
    unittest.main()
