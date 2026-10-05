import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qa_rules_extra as x  # noqa: E402
from test_qa_rules import product  # noqa: E402


def groups(d):
    return sorted({(i["group"], i["field"]) for i in x.check_extra(d)})


class Extra(unittest.TestCase):
    def test_clean_fixture(self):
        self.assertEqual(groups(product()), [])

    def test_template_bug(self):
        d = product(page__seo_title="Leeds United Home Kids Kit kit 26/27 %focuskw%")
        self.assertIn(("Lỗi template / copy", "SEO title"), groups(d))

    def test_kfk_hard_banned_but_not_real_madrid(self):
        d = product(store__description=product()["store"]["description"] + "<p>A genuine favourite like Real Madrid.</p>")
        issue = [i for i in x.check_extra(d) if i["group"] == "Từ cấm tuyệt đối (KFK)"][0]
        self.assertIn("genuine", issue["detail"])
        self.assertNotIn("'Real'", issue["detail"])

    def test_sku_duplicate_suffix(self):
        self.assertIn(("SKU", "SKU"), groups(product(store__sku="KFK_LEE_HO_KD_No_26/27-1")))

    def test_kfk_price(self):
        self.assertIn(("Kho / Giá", "Giá"), groups(product(store__prices={"price": "3999"})))

    def test_seo_title_unrelated(self):
        d = product(page__seo_title="Buy Chelsea Away Shirt Today | Quality Assurance")
        self.assertIn(("SEO", "SEO title"), groups(d))

    def test_reported_club_private(self):
        d = product(store__name="Bay^_^rn Home Kids Football Kit 2026/27 (With socks)")
        d["store"]["attributes"][3]["terms"] = [{"name": "Bay^_^rn"}]
        self.assertIn(("Club bị report (KFK)", "Trạng thái"), groups(d))

    def test_free_pin_missing(self):
        d = product(store__name="England Home Kids Football Kit 2026 (With socks)", page__pin_text=False)
        self.assertIn(("Khuyến mãi Free Pin (KFK)", "Trang sản phẩm"), groups(d))

    def test_tag_other_team_and_season(self):
        d = product(store__tags=[{"name": "Chelsea 26/27"}, {"name": "Leeds United 25/26"}])
        g = groups(d)
        self.assertIn(("Category / Tag", "Tag"), g)
        self.assertIn(("Sai season", "Tag"), g)

    def test_socks_typo(self):
        d = product(store__name="Leeds United Home Kids Football Kit 2026/27 (Witth Socks)")
        self.assertIn(("Lỗi chính tả", "Tên sản phẩm"), groups(d))

    def test_slug_old_season(self):
        d = product(store__permalink="https://kidsfootballkit.co.uk/product/leeds-home-kids-kit-2024-25/")
        d["page"]["canonical"] = d["store"]["permalink"]
        self.assertIn(("URL / Slug", "Slug"), groups(d))

    def test_kit_listing_says_shirt(self):
        d = product(store__description=product()["store"]["description"] + "<p>The shirt is light.</p>")
        self.assertIn(("Sai loại Shirt/Kit", "Description"), groups(d))

    def test_description_price_differs(self):
        d = product(store__prices={"price": "2999", "sale_price": "2999"})
        d["store"]["description"] += "<p>Now only £27.99 while stocks last.</p>"
        self.assertIn(("Kho / Giá", "Description"), groups(d))

    def test_no_socks_but_meta_says_included(self):
        d = product(store__name="Leeds United Home Kids Football Kit 2026/27 (No Socks)",
                    page__meta_description=product()["page"]["meta_description"] + " Socks included.")
        d["store"]["attributes"][5]["terms"] = [{"name": "No Socks"}]
        d["store"]["prices"] = {"price": "2699"}
        self.assertIn(("Sai tất (socks)", "Meta description"), groups(d))

    def test_image_of_other_team_and_side(self):
        imgs = copy.deepcopy(product()["store"]["images"])
        imgs[0] = {"alt": "Chelsea Away Kids Kit front", "src": "https://x/chelsea-away-front.webp"}
        g = groups(product(store__images=imgs))
        self.assertIn(("Ảnh", "Ảnh sai team"), g)
        self.assertIn(("Sai Home/Away/Third", "Ảnh (alt/tên file)"), g)

    def test_category_other_kit_type(self):
        d = product(store__categories=[{"name": "Leeds United"}, {"name": "Premier League"}, {"name": "Leeds Away"}])
        self.assertIn(("Category / Tag", "Category"), groups(d))

    def test_copy_errors(self):
        d = product()
        d["store"]["description"] += "<p>A greaaat fit for the the season.</p>"
        self.assertIn(("Lỗi chính tả", "Description"), groups(d))

    def test_size_table_has_unsellable_sizes(self):
        d = product(store__sku="KFK_LEE_HO_AD_No_26/27",
                    store__name="Leeds United Home Men Football Shirt 2026/27",
                    page__seo_title="Leeds United Home Men Shirt 26/27",
                    page__meta_description="Shop Leeds United Home Men Shirt 26/27.")
        d["store"]["attributes"][0]["terms"] = [{"name": n} for n in ("S", "M", "L", "XL", "XXL")]
        d["store"]["description"] += "<table><tr><th>Size</th></tr><tr><td>XL</td></tr><tr><td>3XL</td></tr></table>"
        self.assertIn(("Sai đối tượng", "Bảng size"), groups(d))

    def test_player_name_suffix_and_seo_position(self):
        d = product(store__sku="CFS_BM_AW_AD_KANE 9_26/27", site="CFS",
                    store__name="Bayern Munich Away Men Cheap Football Shirt 2026/27 – KANE 9",
                    page__seo_title="Bayern Munich Away Men Cheap Football Shirt 2026/27 - KANE 9")
        g = groups(d)
        self.assertIn(("SEO tên cầu thủ", "Tên sản phẩm"), g)
        self.assertIn(("SEO tên cầu thủ", "SEO title"), g)

    def test_player_name_new_format_ok(self):
        d = product(store__sku="CFS_BM_AW_AD_KANE 9_26/27", site="CFS",
                    store__name="Bayern Munich KANE 9 Away Men Cheap Football Shirt 2026/27",
                    page__seo_title="Bayern Munich KANE 9 Away Men Shirt 2026/27 | Cheap Football Shirts",
                    page__h1="Bayern Munich KANE 9 Away Men Shirt 2026/27")
        self.assertNotIn("SEO tên cầu thủ", {g for g, _ in groups(d)})

    def test_h1_missing_player(self):
        d = product(store__sku="CFS_BM_AW_AD_KANE 9_26/27", site="CFS",
                    store__name="Bayern Munich KANE 9 Away Men Cheap Football Shirt 2026/27",
                    page__seo_title="Bayern Munich KANE 9 Away Men Shirt 2026/27", page__h1="Bayern Munich Away Men 2026/27")
        self.assertIn(("SEO tên cầu thủ", "H1"), groups(d))

    def test_long_sleeve_compared_to_short_sleeve_is_fine(self):
        d = product(store__name="Leeds United Home Kids Football Kit 2026/27 Long Sleeve (With socks)",
                    store__sku="KFK_LEE_HOLV_KD_No_26/27")
        d["store"]["description"] += "<p>A classic alternative to the short-sleeve version.</p>"
        self.assertNotIn("Sleeve", {i["group"] for i in __import__("qa_rules").check_product(d)})

    def test_duplicate_names(self):
        a, b = product(), copy.deepcopy(product())
        b["store"]["id"] = 2
        self.assertEqual(len(x.check_extra_batch([a, b])), 2)


if __name__ == "__main__":
    unittest.main()
