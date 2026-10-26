import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import flyert_access as access
import fetch_threads_detail as detail
import fetcher


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(access, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_status_and_challenge_pause_even_without_matching_body(self):
        for status, body in ((403, "blocked"), (429, "slow down"), (200, "<title>Access Denied</title>")):
            with self.subTest(status=status), self.assertRaises(access.AccessPaused):
                access.check_response(status, {}, body)
        self.assertGreater(access.read_json(self.root / "flyert_cooldown.json")["retry_after"], time.time())

    def test_retry_after_can_extend_cooldown(self):
        with self.assertRaises(access.AccessPaused):
            access.check_response(429, {"Retry-After": "86400"}, "")
        self.assertGreater(access.read_json(self.root / "flyert_cooldown.json")["retry_after"], time.time() + 86000)

    def test_legacy_mark_blocks_another_entry_without_http(self):
        access.write_json(self.root / "threads_detail_1231.waf.json", {"retry_after": time.time() + 600})
        with patch.object(access.subprocess, "run") as request, self.assertRaises(access.AccessPaused):
            access.curl_fetch("https://www.flyert.com.cn/forum.php")
        request.assert_not_called()

    def test_os_lock_rejects_second_process_then_releases(self):
        script = "import sys; from pathlib import Path; import flyert_access as a; a.ROOT=Path(sys.argv[1]); sys.exit(a.guarded_main(lambda: 0)())"
        with access.site_lock():
            result = subprocess.run([sys.executable, "-c", script, str(self.root)], capture_output=True)
            self.assertEqual(result.returncode, 2, result.stderr)
        with access.site_lock():
            pass

    def test_curl_reads_last_headers_and_stops_on_429(self):
        def respond(cmd, **kwargs):
            Path(cmd[cmd.index("--dump-header") + 1]).write_bytes(
                b"HTTP/1.1 200 Connection established\r\n\r\nHTTP/2 429\r\nRetry-After: 86400\r\n\r\n"
            )
            return subprocess.CompletedProcess(cmd, 0, b"slow down", b"")
        with patch.object(access.subprocess, "run", side_effect=respond) as request:
            with self.assertRaises(access.AccessPaused):
                access.curl_fetch("https://www.flyert.com.cn/forum.php")
            self.assertEqual(request.call_count, 1)

    def test_no_fallback_after_browser_block(self):
        with patch.object(fetcher, "_method", "auto"), patch.object(fetcher, "fetch_page_pw", side_effect=access.AccessPaused("blocked")), patch.object(fetcher, "fetch_page_httpx") as http:
            with self.assertRaises(access.AccessPaused):
                fetcher.fetch_page("https://www.flyert.com.cn/forum.php")
            http.assert_not_called()

    def test_list_timeout_preserves_reason_without_fallback(self):
        with patch.object(fetcher, "_method", "auto"), patch.object(fetcher, "fetch_page_pw", side_effect=TimeoutError("Page.goto: Timeout 25000ms exceeded.\nCall log: details")), patch.object(fetcher, "fetch_page_httpx") as http:
            with self.assertRaisesRegex(access.AccessPaused, r"\[pw\]: TimeoutError: Page.goto: Timeout 25000ms exceeded"):
                fetcher.fetch_page("https://www.flyert.com.cn/forum.php")
            http.assert_not_called()
        state = access.read_json(self.root / "flyert_cooldown.json")
        self.assertNotIn("Call log", state["reason"])
        self.assertAlmostEqual(state["retry_after"] - time.time(), 1800, delta=5)

    def test_browser_session_missing_is_diagnosed(self):
        with patch.object(fetcher, "_method", "auto"), patch.object(fetcher, "chrome_cdp_fetch", side_effect=access.AccessPaused("Chrome session unavailable")), patch.object(fetcher, "fetch_page_httpx") as http:
            with self.assertRaisesRegex(access.AccessPaused, "Chrome session unavailable"):
                fetcher.fetch_page("https://www.flyert.com/forum.php")
            http.assert_not_called()

    def call_detail(self, links):
        path = self.root / "links_0101.json"
        access.write_json(path, links)
        with patch.object(sys, "argv", ["fetch_threads_detail.py", str(path), "--out-dir", str(self.root)]), contextlib.redirect_stdout(io.StringIO()):
            return detail.main()

    def test_cached_details_work_during_cooldown_without_request(self):
        access.write_json(self.root / "flyert_cooldown.json", {"retry_after": time.time() + 600})
        access.write_json(self.root / "threads_detail_0101.json", [{"tid": "1", "content": "cached body"}])
        with patch.object(detail, "curl_fetch") as request:
            self.assertEqual(self.call_detail([{"tid": "1", "url": "https://www.flyert.com.cn/forum.php?tid=1"}]), 0)
            request.assert_not_called()

    def test_interruption_preserves_unvisited_cache(self):
        access.write_json(self.root / "threads_detail_0101.json", [{"tid": "2", "content": "keep me"}])
        with patch.object(detail, "curl_fetch", side_effect=access.AccessPaused("blocked")) as request:
            self.assertEqual(self.call_detail([{"tid": "1", "url": "https://www.flyert.com.cn/forum.php?tid=1"}, {"tid": "2", "url": "cached"}]), 2)
            self.assertEqual(request.call_count, 1)
        saved = access.read_json(self.root / "threads_detail_0101.json")
        self.assertTrue(any(row["tid"] == "2" and row["content"] == "keep me" for row in saved))

    def test_partial_details_return_failure(self):
        access.write_json(self.root / "threads_detail_0101.json", [{"tid": "1", "content": "cached body"}])
        with patch.object(detail, "curl_fetch", return_value=b"<title>unavailable</title>"), patch.object(detail.time, "sleep"):
            self.assertEqual(self.call_detail([{"tid": "1", "url": "cached"}, {"tid": "2", "url": "https://www.flyert.com.cn/forum.php?tid=2"}]), 2)

    def test_unicode_chrome_response_preserves_chinese_title(self):
        html = "<html><head><title>一文说清招行万事达人民币借记卡 - 飞客论坛</title></head><body><td id='postmessage_1'>中文正文内容</td><td id='postmessage_2'>回复内容</td></body></html>"
        with patch.object(detail, "curl_fetch", return_value=html), patch.object(detail.time, "sleep"):
            self.assertEqual(self.call_detail([{"tid": "1", "title": "列表中的正确标题", "url": "https://www.flyert.com/forum.php?mod=viewthread&tid=1"}]), 0)
        saved = access.read_json(self.root / "threads_detail_0101.json")
        self.assertEqual(saved[0]["title"], "列表中的正确标题")
        self.assertEqual(saved[0]["content"], "中文正文内容")


if __name__ == "__main__":
    unittest.main()
