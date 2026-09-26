import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qa_rules as q  # noqa: E402

URL = "https://kidsfootballkit.co.uk/product/leeds-home-kids-kit-2026-27/"


def product(**over):
    """A clean KFK kids listing; tests change one thing and expect one issue."""
    d = {
        "site": "KFK",
        "page": {
            "seo_title": "Leeds United Home Kids Kit 26/27 | Birthday Gift for Kids",
            "meta_description": "Shop Leeds United Home Kids Kit 26/27 with fast UK delivery and friendly support.",
            "robots": "follow, index",
            "canonical": URL,
        },
        "store": {
            "id": 1, "name": "Leeds United Home Kids Football Kit 2026/27 (With socks)",
            "sku": "KFK_LEE_HO_KD_No_26/27", "permalink": URL, "type": "variable",
            "description": "<p>This Leeds United 2026/27 Kids Home Kit includes a shirt, matching shorts and matching socks.</p>",
            "short_description": "<ul><li>Fast delivery</li></ul>",
            "attributes": [
                {"name": "Size", "terms": [{"name": "16 (3-4 yrs)"}, {"name": "28 (12-13 yrs)"}]},
                {"name": "Gender/Age", "terms": [{"name": "Kids"}]},
                {"name": "Season", "terms": [{"name": "2026/27"}]},
                {"name": "Clubs Name", "terms": [{"name": "Leeds United"}]},
                {"name": "Kit Type", "terms": [{"name": "Home"}]},
                {"name": "Kit Option", "terms": [{"name": "With Socks"}]},
            ],
            "categories": [{"name": "Leeds United"}, {"name": "Championship"}],
            "tags": [{"name": "Leeds United 26/27"}],
            "images": [
                {"alt": "Leeds United Home Kids Kit 26_27 front view", "src": "https://x/leeds-home-front.webp"},
                {"alt": "Leeds United Home Kids Kit 26_27 back view", "src": "https://x/leeds-home-back.webp"},
                {"alt": "Kids Football Kit Size Chart", "src": "https://x/KFK-Kid-Kit-Size-Chart.png"},
            ],
            "prices": {"price": "3999"}, "is_in_stock": True, "variations": [{"id": 2}],
        },
    }
    for path, value in over.items():
        target = d
        keys = path.split("__")
        for k in keys[:-1]:
            target = target[k]
        target[keys[-1]] = value
    return d


def groups(d):
    return sorted({(i["group"], i["field"]) for i in q.check_product(d)})


class CleanListing(unittest.TestCase):
    def test_clean_listing_has_no_issues(self):
        self.assertEqual(q.check_product(product()), [])


class Rules(unittest.TestCase):
    def assertOnly(self, d, group, field):
        self.assertEqual(groups(d), [(group, field)])

    def test_wrong_kit_in_meta(self):
        self.assertOnly(product(page__meta_description="Shop Leeds United Away Kids Kit 26/27 today."),
                        "Sai Home/Away/Third", "Meta description")

    def test_description_copied_from_other_kit(self):
        d = product(store__description="<p>The Leeds United Away Kids Kit for 2026/27 includes a shirt and shorts.</p>")
        self.assertOnly(d, "Sai Home/Away/Third", "Description")

    def test_shirt_vs_kit_in_seo_title(self):
        self.assertOnly(product(page__seo_title="Leeds United Home Kids Shirt 26/27"),
                        "Sai loại Shirt/Kit", "SEO title")

    def test_old_season_in_description(self):
        d = product(store__description="<p>The Leeds United 2025/26 Kids Home Kit includes a shirt and shorts.</p>")
        self.assertIn(("Sai season", "Description"), groups(d))

    def test_size_table_is_not_a_season(self):
        d = product(store__description="<p>Leeds kit.</p><table><tr><td>10-11 yrs</td><td>12-13 yrs</td></tr></table>")
        self.assertEqual(groups(d), [])

    def test_adult_sku_on_kids_name(self):
        self.assertIn(("Sai đối tượng", "Tên sản phẩm"), groups(product(store__sku="KFK_LEE_HO_AD_No_26/27")))

    def test_kids_sizes_on_adult_listing(self):
        d = product(store__sku="KFK_LEE_HO_AD_No_26/27",
                    store__name="Leeds United Home Men Football Shirt 2026/27",
                    page__seo_title="Leeds United Home Men Shirt 26/27",
                    page__meta_description="Shop Leeds United Home Men Shirt 26/27.")
        self.assertIn(("Sai đối tượng", "Size"), groups(d))

    def test_player_listing_without_player_attribute(self):
        d = product(store__sku="KFK_LEE_HO_KD_CALVERT-LEWIN 9_26/27",
                    store__name="Leeds United Home Kids Football Kit 2026/27 – CALVERT-LEWIN 9 (With socks)",
                    store__categories=[{"name": "Leeds United"}, {"name": "CALVERT-LEWIN 9"}])
        self.assertEqual(groups(d), [("Sai cầu thủ", "Attribute Players")])

    def test_non_player_with_player_in_seo(self):
        self.assertIn(("Sai cầu thủ", "SEO title"),
                      groups(product(page__seo_title="Leeds United RODON 6 Home Kids Kit 26/27")))

    def test_no_socks_name_but_attribute_with_socks(self):
        d = product(store__name="Leeds United Home Kids Football Kit 2026/27 (No Socks)",
                    store__description="<p>Leeds United 2026/27 Kids Home Kit: shirt and shorts.</p>")
        self.assertEqual(groups(d), [("Sai tất (socks)", "Attribute Kit Option")])

    def test_words_to_avoid(self):
        d = product(store__description="<p>The official Leeds United 2026/27 kit with the club crest.</p>")
        issue = [i for i in q.check_product(d) if i["group"] == "Words to Avoid"][0]
        self.assertIn("official", issue["detail"])
        self.assertIn("crest", issue["detail"])

    def test_short_sleeve(self):
        self.assertIn(("Sleeve", "Description"),
                      groups(product(store__description="<p>Leeds 2026/27 kit with a short-sleeve shirt.</p>")))

    def test_canonical_to_other_page(self):
        self.assertOnly(product(page__canonical="https://kidsfootballkit.co.uk/product/leeds-away-2024-25/"),
                        "SEO", "Canonical")

    def test_noindex(self):
        self.assertOnly(product(page__robots="follow, noindex"), "SEO", "Robots")

    def test_space_before_comma(self):
        self.assertOnly(product(page__meta_description="Get the Leeds United Home Kids Kit 26/27 , great price."),
                        "SEO", "Meta description")

    def test_adult_size_chart_on_kids(self):
        imgs = copy.deepcopy(product()["store"]["images"])
        imgs[2] = {"alt": "Adult Size Chart", "src": "https://x/KFK-Adult-Size-Chart.png"}
        self.assertOnly(product(store__images=imgs), "Ảnh", "Size chart")

    def test_long_sleeve_sku(self):
        d = product(store__name="Leeds United Home Kids Football Kit 2026/27 Long Sleeve (With socks)")
        self.assertIn(("Sleeve", "SKU"), groups(d))
        d["store"]["sku"] = "KFK_LEE_HOLV_KD_No_26/27"
        self.assertNotIn(("Sleeve", "SKU"), groups(d))

    def test_rfs_required_sentence(self):
        d = product(site="RFS")
        self.assertIn(("Thiếu nội dung bắt buộc", "Description"), groups(d))

    def test_out_of_stock(self):
        self.assertOnly(product(store__is_in_stock=False), "Kho / Giá", "Stock")


class TeamNames(unittest.TestCase):
    def test_brand_safe_spellings(self):
        self.assertTrue(q.fuzzy_contains("Lvr^_^pooI Home Kids", "lvrp00l"))
        self.assertTrue(q.fuzzy_contains("Arsn@l SAKA 7", "Arsenal"))
        self.assertTrue(q.fuzzy_contains("Al Nassr 2026/27", "Al Nassr FC"))

    def test_different_clubs(self):
        self.assertFalse(q.fuzzy_contains("Manchester United Home", "Manchester City"))
        self.assertFalse(q.fuzzy_contains("Inter Milan", "AC Milan"))
        self.assertFalse(q.fuzzy_contains("Real Madrid", "Real Betis"))


class Batch(unittest.TestCase):
    def test_duplicate_seo_title(self):
        a, b = product(), product()
        b["store"]["id"] = 2
        issues = q.check_batch([a, b])
        self.assertEqual({i["field"] for _, i in issues}, {"SEO title", "Meta description"})


if __name__ == "__main__":
    unittest.main()
