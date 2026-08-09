import unittest
from unittest.mock import MagicMock, patch
import threading
from datetime import date

import rootdata
import cryptorank
import okboost
import notifier
import main


class TestAirdropDiscovery(unittest.TestCase):

    def test_thread_local_sessions(self):
        """Verify that _get_session returns a requests.Session and is thread-local."""
        # 1. Test main thread session caching
        rd_session = rootdata._get_session()
        self.assertIsInstance(rd_session, rootdata.requests.Session)
        self.assertIs(rd_session, rootdata._get_session())

        cr_session = cryptorank._get_session()
        self.assertIsInstance(cr_session, cryptorank.requests.Session)
        self.assertIs(cr_session, cryptorank._get_session())

        # 2. Test thread-local isolation
        sessions_found = []
        def thread_target():
            sess = rootdata._get_session()
            sessions_found.append(sess)

        t = threading.Thread(target=thread_target)
        t.start()
        t.join()

        self.assertEqual(len(sessions_found), 1)
        self.assertIsNot(rd_session, sessions_found[0])

    @patch("main.send_message")
    @patch("main.rootdata.get_daily_funding")
    @patch("main.rootdata.get_project_events")
    @patch("main.rootdata.get_new_projects")
    @patch("main.rootdata.get_upcoming_tge")
    @patch("main.cryptorank.get_daily_funding")
    @patch("main.cryptorank.get_upcoming_ido")
    @patch("main.okboost.get_daily_okboost")
    def test_run_daily_job_parallel(self, mock_okboost, mock_cr_ido, mock_cr_funding,
                                    mock_rd_tge, mock_rd_new, mock_rd_events, mock_rd_funding,
                                    mock_send):
        """Test run_daily_job parallel execution and formatting."""
        mock_rd_funding.return_value = [{"name": "RD Project", "round": "Seed", "amount": "$5M", "investors": ["VC A"], "url": "url"}]
        mock_rd_events.return_value = [{"name": "RD Event", "event": "Mainnet Launch", "date": "2026-08-09", "url": "url"}]
        mock_rd_new.return_value = [{"name": "RD New Proj", "category": ["DeFi"], "desc": "Desc", "url": "url"}]
        mock_rd_tge.return_value = [{"name": "RD TGE", "token": "RDT", "tge_date": "2026-08-09", "url": "url"}]
        mock_cr_funding.return_value = [{"name": "CR Project", "symbol": "CRP", "round": "Series A", "amount": "$10M", "investors": ["VC B"], "url": "url"}]
        mock_cr_ido.return_value = [{"name": "CR IDO", "symbol": "CRI", "start_date": "2026-08-09", "url": "url"}]
        mock_okboost.return_value = [{"title": "OKX Boost Announcement", "desc": "Launchpool detail", "url": "url"}]

        main.run_daily_job()

        # Check send_message was called with the daily report
        mock_send.assert_called_once()
        report_text = mock_send.call_args[0][0]
        self.assertIn("RD Project", report_text)
        self.assertIn("RD Event", report_text)
        self.assertIn("RD New Proj", report_text)
        self.assertIn("RD TGE", report_text)
        self.assertIn("CR Project", report_text)
        self.assertIn("CR IDO", report_text)
        self.assertIn("OKX Boost Announcement", report_text)

    @patch("notifier._send_chunk")
    def test_send_message_splitting(self, mock_send_chunk):
        """Test that long messages are split correctly by paragraph."""
        mock_send_chunk.return_value = True

        # Generate long text
        long_paragraph = "A" * 2500
        text = f"{long_paragraph}\n\n{long_paragraph}"

        notifier.send_message(text)

        # Should split at \n\n
        self.assertEqual(mock_send_chunk.call_count, 2)
        mock_send_chunk.assert_any_call(long_paragraph)

    @patch("rootdata._get_session")
    def test_rootdata_post(self, mock_get_session):
        """Verify rootdata _post method handles requests correctly."""
        mock_sess = MagicMock()
        mock_get_session.return_value = mock_sess

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 200, "data": {"items": [{"name": "Test"}]}}
        mock_sess.post.return_value = mock_resp

        res = rootdata.get_daily_funding()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "Test")

    @patch("cryptorank._get_session")
    def test_cryptorank_get(self, mock_get_session):
        """Verify cryptorank _get method handles requests correctly."""
        mock_sess = MagicMock()
        mock_get_session.return_value = mock_sess

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"name": "TestCur", "symbol": "TC"}]}
        mock_sess.get.return_value = mock_resp

        res = cryptorank.get_daily_funding()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "TestCur")

    @patch("okboost._get_session")
    @patch("okboost.date")
    def test_okboost_get_daily(self, mock_date, mock_get_session):
        """Verify okboost RSS fetching and keyword/date filtering."""
        mock_sess = MagicMock()
        mock_get_session.return_value = mock_sess

        # Simulate RSS feed content
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>OKX Launchpool listing</title>
              <link>https://okx.com/listing</link>
              <description>&lt;p&gt;This is some html desc about launchpool&lt;/p&gt;</description>
              <pubDate>Sun, 09 Aug 2026 10:00:00 +0000</pubDate>
            </item>
            <item>
              <title>Unrelated news</title>
              <link>https://okx.com/news</link>
              <description>Unrelated content description</description>
              <pubDate>Sun, 09 Aug 2026 10:00:00 +0000</pubDate>
            </item>
          </channel>
        </rss>"""

        mock_resp = MagicMock()
        mock_resp.content = rss_content.encode("utf-8")
        mock_sess.get.return_value = mock_resp

        # Set mocked date inside okboost to 2026-08-09
        mock_date.today.return_value = date(2026, 8, 9)

        res = okboost.get_daily_okboost()
        # "OKX Launchpool listing" matches because of "launchpool" keyword
        # "Unrelated news" doesn't match because of no matching keywords
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "OKX Launchpool listing")
        self.assertEqual(res[0]["desc"], "This is some html desc about launchpool")


if __name__ == "__main__":
    unittest.main()
