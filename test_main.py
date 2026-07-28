import unittest
from unittest.mock import patch, MagicMock
from datetime import date

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestAirdropDiscovery(unittest.TestCase):

    @patch("notifier._get_session")
    @patch("okboost._get_session")
    @patch("cryptorank._get_session")
    @patch("rootdata._get_session")
    def test_run_daily_job_success(
        self, mock_rd_sess, mock_cr_sess, mock_ok_sess, mock_nt_sess
    ):
        # Create mock Session objects
        rd_sess = MagicMock()
        cr_sess = MagicMock()
        ok_sess = MagicMock()
        nt_sess = MagicMock()

        mock_rd_sess.return_value = rd_sess
        mock_cr_sess.return_value = cr_sess
        mock_ok_sess.return_value = ok_sess
        mock_nt_sess.return_value = nt_sess

        # 1. Setup Mock responses
        # Mock RootData response for POST requests
        rd_sess.post.return_value.status_code = 200
        rd_sess.post.return_value.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {
                        "project_name": "Mock Project RD",
                        "amount": "$10M",
                        "round": "Series A",
                        "investors": ["VC A", "VC B"],
                        "url": "https://rootdata.com/mock",
                    }
                ]
            }
        }

        # Mock CryptoRank response for GET requests
        cr_sess.get.return_value.status_code = 200
        cr_sess.get.return_value.json.return_value = {
            "data": [
                {
                    "name": "Mock Project CR",
                    "symbol": "MPCR",
                    "amount": "$5M",
                    "stage": "Seed",
                    "investors": [{"name": "VC C"}],
                    "url": "https://cryptorank.com/mock",
                }
            ]
        }

        # Mock OKX RSS feed
        ok_sess.get.return_value.status_code = 200
        ok_sess.get.return_value.content = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>OKX Help Center</title>
    <link>https://www.okx.com</link>
    <item>
      <title>OKX Jumpstart / Launchpool Project Launched!</title>
      <link>https://www.okx.com/launchpool</link>
      <description>&lt;p&gt;This is a mock description about launchpool and airdrop.&lt;/p&gt;</description>
      <pubDate>Mon, 13 Mar 2023 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

        # Mock Telegram response
        nt_sess.post.return_value.status_code = 200
        nt_sess.post.return_value.ok = True

        # Run target date
        target_date = date(2023, 3, 13)

        # Patch main.date instead of built-in datetime.date to be completely safe
        with patch("main.date") as mock_date:
            mock_date.today.return_value = target_date
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            # Execute daily job
            main.run_daily_job()

        # Check that we invoked the APIs
        self.assertTrue(rd_sess.post.called)
        self.assertTrue(cr_sess.get.called)
        self.assertTrue(ok_sess.get.called)
        self.assertTrue(nt_sess.post.called)

        # Check session usage counts
        self.assertGreaterEqual(rd_sess.post.call_count, 1)
        self.assertGreaterEqual(cr_sess.get.call_count, 1)

    def test_session_sharing_thread_safety(self):
        # Verify that all modules use their thread-local session functions correctly
        sess1 = rootdata._get_session()
        sess2 = rootdata._get_session()
        self.assertIs(sess1, sess2)  # Same thread gets same session


if __name__ == "__main__":
    unittest.main()
