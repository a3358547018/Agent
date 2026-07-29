import unittest
from unittest.mock import patch, MagicMock
from datetime import date

import main
import rootdata
import cryptorank
import okboost
import notifier


class TestAirdropDiscovery(unittest.TestCase):

    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("notifier._get_session")
    def test_run_daily_job_success(
        self,
        mock_notifier_session_getter,
        mock_okboost_session_getter,
        mock_cryptorank_session_getter,
        mock_rootdata_session_getter,
    ):
        # 1. Setup mocked sessions
        mock_rd_session = MagicMock()
        mock_cr_session = MagicMock()
        mock_ok_session = MagicMock()
        mock_notif_session = MagicMock()

        mock_rootdata_session_getter.return_value = mock_rd_session
        mock_cryptorank_session_getter.return_value = mock_cr_session
        mock_okboost_session_getter.return_value = mock_ok_session
        mock_notifier_session_getter.return_value = mock_notif_session

        # Mock rootdata response
        mock_rd_resp = MagicMock()
        mock_rd_resp.json.return_value = {
            "result": True,
            "data": {
                "items": [
                    {
                        "project_name": "Project A",
                        "amount": "$10M",
                        "round": "Seed",
                        "investors": ["VC A", "VC B"],
                        "date": "2026-05-10",
                        "url": "http://rootdata/proj-a",
                        "description": "Awesome Project A",
                        "tags": ["DeFi"],
                        "add_time": "2026-05-10",
                    }
                ]
            }
        }
        mock_rd_session.post.return_value = mock_rd_resp

        # Mock cryptorank response
        mock_cr_resp = MagicMock()
        mock_cr_resp.json.return_value = {
            "data": [
                {
                    "name": "Project B",
                    "symbol": "PRJB",
                    "amount": "$5M",
                    "stage": "Series A",
                    "investors": [{"name": "VC C"}],
                    "date": "2026-05-10",
                    "key": "proj-b",
                }
            ]
        }
        mock_cr_session.get.return_value = mock_cr_resp

        # Mock okboost response (RSS Feed XML)
        mock_ok_resp = MagicMock()
        mock_ok_resp.content = b"""<rss version="2.0">
            <channel>
                <item>
                    <title>OKX Launchpool Project C</title>
                    <link>http://okx/launchpool-c</link>
                    <description>Stake OKB to farm Project C token!</description>
                    <pubDate>Sun, 10 May 2026 10:00:00 +0000</pubDate>
                </item>
            </channel>
        </rss>"""
        mock_ok_session.get.return_value = mock_ok_resp

        # Mock notifier response
        mock_notif_resp = MagicMock()
        mock_notif_resp.ok = True
        mock_notif_session.post.return_value = mock_notif_resp

        # Execute daily job
        # We patch target date to be 2026-05-10
        with patch("main.date") as mock_date:
            mock_date.today.return_value = date(2026, 5, 10)
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            with patch("rootdata.date") as mock_rd_date, \
                 patch("cryptorank.date") as mock_cr_date, \
                 patch("okboost.date") as mock_ok_date:

                mock_rd_date.today.return_value = date(2026, 5, 10)
                mock_rd_date.side_effect = lambda *args, **kw: date(*args, **kw)

                mock_cr_date.today.return_value = date(2026, 5, 10)
                mock_cr_date.side_effect = lambda *args, **kw: date(*args, **kw)

                mock_ok_date.today.return_value = date(2026, 5, 10)
                mock_ok_date.side_effect = lambda *args, **kw: date(*args, **kw)

                main.run_daily_job()

        # 2. Assertions to confirm correctness
        self.assertTrue(mock_rd_session.post.called)
        self.assertTrue(mock_cr_session.get.called)
        self.assertTrue(mock_ok_session.get.called)
        self.assertTrue(mock_notif_session.post.called)

    @patch("rootdata._get_session")
    @patch("cryptorank._get_session")
    @patch("okboost._get_session")
    @patch("notifier._get_session")
    def test_run_daily_job_failures_handled_gracefully(
        self,
        mock_notifier_session_getter,
        mock_okboost_session_getter,
        mock_cryptorank_session_getter,
        mock_rootdata_session_getter,
    ):
        # Setup mock behavior to throw exceptions
        mock_rd_session = MagicMock()
        mock_cr_session = MagicMock()
        mock_ok_session = MagicMock()
        mock_notif_session = MagicMock()

        mock_rootdata_session_getter.return_value = mock_rd_session
        mock_cryptorank_session_getter.return_value = mock_cr_session
        mock_okboost_session_getter.return_value = mock_ok_session
        mock_notifier_session_getter.return_value = mock_notif_session

        mock_rd_session.post.side_effect = Exception("RootData connection timed out")
        mock_cr_session.get.side_effect = Exception("CryptoRank rate limit exceeded")
        mock_ok_session.get.side_effect = Exception("OKX RSS returned 500")

        mock_notif_resp = MagicMock()
        mock_notif_resp.ok = True
        mock_notif_session.post.return_value = mock_notif_resp

        # We execute the job and it should run to completion despite the module exceptions
        with patch("main.date") as mock_date:
            mock_date.today.return_value = date(2026, 5, 10)
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            with patch("rootdata.date") as mock_rd_date, \
                 patch("cryptorank.date") as mock_cr_date, \
                 patch("okboost.date") as mock_ok_date:

                mock_rd_date.today.return_value = date(2026, 5, 10)
                mock_rd_date.side_effect = lambda *args, **kw: date(*args, **kw)

                mock_cr_date.today.return_value = date(2026, 5, 10)
                mock_cr_date.side_effect = lambda *args, **kw: date(*args, **kw)

                mock_ok_date.today.return_value = date(2026, 5, 10)
                mock_ok_date.side_effect = lambda *args, **kw: date(*args, **kw)

                main.run_daily_job()

        # The notifier should still be called to send the daily report message
        # (even if some data sections are empty)
        self.assertTrue(mock_notif_session.post.called)


if __name__ == "__main__":
    unittest.main()
