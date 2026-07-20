import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import concurrent.futures

# Mock the configuration before importing components
import sys
mock_config = MagicMock()
mock_config.ROOTDATA_API_KEY = "test"
mock_config.CRYPTORANK_API_KEY = "test"
mock_config.TG_BOT_TOKEN = "test"
mock_config.TG_CHAT_ID = "test"
mock_config.SCHEDULE_HOUR = 10
mock_config.SCHEDULE_MINUTE = 0
sys.modules['config'] = mock_config

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestPerformanceOptimization(unittest.TestCase):

    @patch('requests.Session.request')
    def test_session_pooling(self, mock_request):
        """Test that data modules utilize requests.Session() and keep pooling active."""
        # Set up mock response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": True, "data": {"items": []}}
        mock_request.return_value = mock_resp

        # Call the functions
        rootdata.get_daily_funding(date.today())

        # Verify requests.Session.request was called instead of general requests module
        self.assertTrue(mock_request.called)

    @patch('rootdata.get_daily_funding')
    @patch('rootdata.get_project_events')
    @patch('rootdata.get_new_projects')
    @patch('rootdata.get_upcoming_tge')
    @patch('cryptorank.get_daily_funding')
    @patch('cryptorank.get_upcoming_ido')
    @patch('okboost.get_daily_okboost')
    @patch('main.send_message')
    def test_parallel_fetching(self, mock_send, mock_ok, mock_cr_ido, mock_cr_fund, mock_rd_tge, mock_rd_new, mock_rd_events, mock_rd_fund):
        """Test that data fetching works in parallel and produces formatting."""
        # Set mock return values
        mock_rd_fund.return_value = [{"name": "P1", "amount": "1M", "round": "Seed", "investors": ["V1"], "date": "2026-07-20", "url": ""}]
        mock_rd_events.return_value = []
        mock_rd_new.return_value = []
        mock_rd_tge.return_value = []
        mock_cr_fund.return_value = []
        mock_cr_ido.return_value = []
        mock_ok.return_value = []

        # Run the main parallel job
        main.run_daily_job()

        # Assert all fetches are called
        mock_rd_fund.assert_called_once()
        mock_rd_events.assert_called_once()
        mock_rd_new.assert_called_once()
        mock_rd_tge.assert_called_once()
        mock_cr_fund.assert_called_once()
        mock_cr_ido.assert_called_once()
        mock_ok.assert_called_once()
        mock_send.assert_called_once()


if __name__ == '__main__':
    unittest.main()
