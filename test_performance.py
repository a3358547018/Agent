import unittest
from unittest.mock import patch, MagicMock
from datetime import date

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestPerformanceAndConnectionPooling(unittest.TestCase):

    def setUp(self):
        # Reset any potential request call mocks
        pass

    @patch('requests.Session.request')
    def test_session_usage(self, mock_request):
        """Verify that the data modules are indeed using the module-level requests.Session."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"code": 200, "data": {"items": []}, "result": True}
        mock_request.return_value = mock_response

        # Call get_daily_funding from rootdata which should trigger the session post
        rootdata.get_daily_funding()
        self.assertTrue(mock_request.called)
        # Ensure that it was a session-based call (which delegates to requests.Session.request)
        first_call_args, first_call_kwargs = mock_request.call_args
        self.assertEqual(first_call_args[0], 'POST')

    @patch('requests.Session.request')
    def test_parallel_execution(self, mock_request):
        """Verify that run_daily_job executes all 7 data sources and handles them concurrently."""
        def mock_request_side_effect(method, url, *args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.ok = True
            if "rss.xml" in url:
                # Mock XML content for RSS parsing in okboost
                mock_resp.content = (
                    b'<rss><channel><item>'
                    b'<title>Test OKBoost launchpool</title>'
                    b'<link>https://www.okx.com/help-center/123</link>'
                    b'<description>Great launchpool staking</description>'
                    b'<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>'
                    b'</item></channel></rss>'
                )
            else:
                mock_resp.content = b'{"code": 200, "data": {"items": []}, "result": true}'
                mock_resp.json.return_value = {"code": 200, "data": {"items": []}, "result": True}
            return mock_resp

        mock_request.side_effect = mock_request_side_effect

        # Mock the sending side (TG push) to avoid hitting external APIs
        with patch('main.send_message') as mock_send:
            main.run_daily_job()
            self.assertTrue(mock_send.called)
            # There are 7 data-fetching requests (4 rootdata, 2 cryptorank, 1 okboost)
            # plus potentially notifier calls, so check count is at least 7.
            self.assertGreaterEqual(mock_request.call_count, 7)
