import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_new_listings as m  # noqa: E402

CFG = {"rss_max_pages": 3, "store_api_max_pages": 3}
BASE = "https://example.com"

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Barcelona Home Kid Replica Football Kit 2026/27</title>
 <link>https://example.com/product/barca-home-kid/</link>
 <guid>https://example.com/?post_type=product&amp;p=103</guid>
 <pubDate>Sat, 26 Sep 2026 09:15:00 +0000</pubDate></item>
<item><title>Brazil World Cup 2026 Home Men Replica Football Shirt</title>
 <link>https://example.com/product/brazil-home/</link>
 <guid>https://example.com/?post_type=product&amp;p=101</guid>
 <pubDate>Fri, 25 Sep 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""

STORE = [
    {"id": 104, "name": "Inter Milan Away Kid Kit", "sku": "INT-A-KD",
     "permalink": "https://example.com/product/inter-away/", "categories": [{"name": "Inter Milan"}]},
    {"id": 103, "name": "Barcelona Home Kid Kit", "sku": "BAR-H-KD",
     "permalink": "https://example.com/product/barca-home-kid/", "categories": [{"name": "Barcelona"}]},
    {"id": 101, "name": "Brazil Home", "sku": "BRA-H-AD",
     "permalink": "https://example.com/product/brazil-home/", "categories": []},
]


def fake_fetch(url, timeout=30):
    if "/feed/" in url:
        if "paged=" in url:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        return RSS, {}
    return json.dumps(STORE), {"X-WP-TotalPages": "1"}


class CheckSiteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        m.STATE_DIR = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, target=date(2026, 9, 26), use_diff=True):
        return m.check_site("KFK", BASE, target, timezone.utc, CFG, use_diff, fetch=fake_fetch)

    def test_first_run_uses_rss_and_saves_baseline(self):
        rows, notes = self.run_check()
        self.assertEqual([r["product_id"] for r in rows], [103])
        self.assertEqual(rows[0]["sku"], "BAR-H-KD")
        self.assertTrue(any("Lan chay dau" in n for n in notes))
        saved = json.loads((m.STATE_DIR / "KFK.json").read_text())
        self.assertEqual(saved["known_ids"], [101, 103, 104])

    def test_diff_catches_product_missing_from_rss(self):
        (m.STATE_DIR / "KFK.json").write_text(json.dumps({"known_ids": [101]}))
        rows, _ = self.run_check()
        got = {r["product_id"]: r["detected_by"] for r in rows}
        self.assertEqual(got, {103: "rss+diff", 104: "diff"})

    def test_nothing_new(self):
        (m.STATE_DIR / "KFK.json").write_text(json.dumps({"known_ids": [101, 103, 104]}))
        rows, _ = self.run_check(target=date(2026, 9, 27))
        self.assertEqual(rows, [])

    def test_past_date_rss_only(self):
        rows, _ = self.run_check(target=date(2026, 9, 25), use_diff=False)
        self.assertEqual([r["product_id"] for r in rows], [101])
        self.assertFalse((m.STATE_DIR / "KFK.json").exists())

    def test_site_unreachable_reports_error(self):
        def boom(url, timeout=30):
            raise urllib.error.URLError("blocked")
        rows, notes = m.check_site("KFK", BASE, date(2026, 9, 26), timezone.utc, CFG, True, fetch=boom)
        self.assertEqual(rows, [])
        self.assertEqual(len([n for n in notes if "loi" in n]), 2)

    def test_disabled_feed_falls_back_to_diff(self):
        (m.STATE_DIR / "KFK.json").write_text(json.dumps({"known_ids": [101, 103]}))

        def fetch(url, timeout=30):
            if "/feed/" in url:
                return "<!DOCTYPE html><html>homepage</html>", {}
            return fake_fetch(url)
        rows, notes = m.check_site("KFK", BASE, date(2026, 9, 26), timezone.utc, CFG, True, fetch=fetch)
        self.assertEqual([(r["product_id"], r["detected_by"]) for r in rows], [(104, "diff")])
        self.assertTrue(any("RSS feed bi tat" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
