import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_new_listings as m  # noqa: E402

CFG = {"wp_max_pages": 3, "rss_max_pages": 3, "store_api_max_pages": 3}
BASE = "https://example.com"
D26 = date(2026, 9, 26)

WP = [
    {"id": 103, "date": "2026-09-26T09:15:00", "link": "https://example.com/product/barca-home-kid/",
     "title": {"rendered": "Barcelona Home Kid Replica Football Kit 2026/27"}},
    {"id": 101, "date": "2026-09-25T10:00:00", "link": "https://example.com/product/brazil-home/",
     "title": {"rendered": "Brazil &#8211; Home"}},
]

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


def wp_in_range(url):
    after = url.split("after=")[1][:10]
    before = url.split("before=")[1][:10]
    return [p for p in WP if after < p["date"][:10] < before]


def make_fetch(wp_ok=True, rss="ok"):
    def fetch(url, timeout=30):
        if "/wp/v2/" in url:
            if not wp_ok:
                raise urllib.error.HTTPError(url, 401, "no", {}, None)
            return json.dumps(wp_in_range(url)), {"X-WP-TotalPages": "1"}
        if "/feed/" in url:
            if rss == "disabled":
                return "<!DOCTYPE html><html>homepage</html>", {}
            if "paged=" in url:
                raise urllib.error.HTTPError(url, 404, "nf", {}, None)
            return RSS, {}
        if "/products/" in url:  # single product (out of stock, hidden from lists)
            return json.dumps({"id": 105, "sku": "OOS-KD", "is_in_stock": False, "categories": []}), {}
        if "include=" in url:
            ids = {int(x) for x in url.split("include=")[1].split("&")[0].split(",")}
            return json.dumps([p for p in STORE if p["id"] in ids]), {}
        return json.dumps(STORE), {"X-WP-TotalPages": "1"}
    return fetch


class CheckSiteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        m.STATE_DIR = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, start=D26, end=D26, use_diff=True, **kw):
        return m.check_site("KFK", BASE, start, end, timezone.utc, CFG, use_diff, fetch=make_fetch(**kw))

    def test_first_run_uses_wp_and_saves_baseline(self):
        rows, notes = self.check()
        self.assertEqual([(r["product_id"], r["detected_by"], r["sku"]) for r in rows],
                         [(103, "wp", "BAR-H-KD")])
        self.assertTrue(any("Lan chay dau" in n for n in notes))
        saved = json.loads((m.STATE_DIR / "KFK.json").read_text())
        self.assertEqual(saved["known_ids"], [101, 103, 104])

    def test_diff_catches_product_missing_from_dated_source(self):
        (m.STATE_DIR / "KFK.json").write_text(json.dumps({"known_ids": [101]}))
        rows, _ = self.check()
        got = {r["product_id"]: r["detected_by"] for r in rows}
        self.assertEqual(got, {103: "wp+diff", 104: "diff"})

    def test_nothing_new(self):
        (m.STATE_DIR / "KFK.json").write_text(json.dumps({"known_ids": [101, 103, 104]}))
        rows, _ = self.check(start=date(2026, 9, 27), end=date(2026, 9, 27))
        self.assertEqual(rows, [])

    def test_range_past_no_diff(self):
        rows, _ = self.check(start=date(2026, 9, 1), end=date(2026, 9, 25), use_diff=False)
        self.assertEqual([(r["product_id"], r["name"], r["sku"]) for r in rows],
                         [(101, "Brazil – Home", "BRA-H-AD")])
        self.assertFalse((m.STATE_DIR / "KFK.json").exists())

    def test_wp_fails_falls_back_to_rss(self):
        rows, notes = self.check(wp_ok=False)
        self.assertEqual([(r["product_id"], r["detected_by"]) for r in rows], [(103, "rss")])
        self.assertTrue(any("WP REST loi" in n for n in notes))

    def test_wp_fails_and_rss_disabled_uses_diff(self):
        (m.STATE_DIR / "KFK.json").write_text(json.dumps({"known_ids": [101, 103]}))
        rows, notes = self.check(wp_ok=False, rss="disabled")
        self.assertEqual([(r["product_id"], r["detected_by"]) for r in rows], [(104, "diff")])
        self.assertNotIn("KHONG KIEM TRA DUOC", notes)

    def test_site_unreachable(self):
        def boom(url, timeout=30):
            raise urllib.error.URLError("blocked")
        rows, notes = m.check_site("KFK", BASE, D26, D26, timezone.utc, CFG, True, fetch=boom)
        self.assertEqual(rows, [])
        self.assertIn("KHONG KIEM TRA DUOC", notes)

    def test_out_of_stock_fetched_individually(self):
        WP.append({"id": 105, "date": "2026-09-26T08:00:00", "link": "u", "title": {"rendered": "OOS"}})
        try:
            rows, _ = self.check(use_diff=False)
        finally:
            WP.pop()
        oos = [r for r in rows if r["product_id"] == 105][0]
        self.assertEqual((oos["sku"], oos["in_stock"]), ("OOS-KD", "NO"))
        text = m.build_summary(D26, D26, {"KFK": (rows, [])}, False)
        self.assertIn("(1 dang HET HANG)", text)

    def test_summary_range_shows_per_day(self):
        rows, notes = self.check(start=date(2026, 9, 1), end=D26, use_diff=False)
        text = m.build_summary(date(2026, 9, 1), D26, {"KFK": (rows, notes)}, False)
        self.assertIn("KFK: 2 listing moi", text)
        self.assertIn("Theo ngay: 09-25: 1, 09-26: 1", text)


if __name__ == "__main__":
    unittest.main()
