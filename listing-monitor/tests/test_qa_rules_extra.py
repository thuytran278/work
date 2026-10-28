import copy
import sys
import unittest
from datetime import date
from unittest import mock
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

    def test_kids_image_file_on_adult_listing(self):
        imgs = copy.deepcopy(product()["store"]["images"])
        imgs[0] = {"alt": "Leeds United Home Adult Kit 26_27 front view", "src": "https://x/Leeds-Home-Kids-Kit-Front.webp"}
        d = product(store__images=imgs, store__sku="KFK_LEE_HO_AD_No_26/27")
        self.assertIn(("Sai đối tượng", "Ảnh (alt/tên file)"), groups(d))

    def test_price_rules_all_sites(self):
        ok = product(site="RFK", store__prices={"price": "2749"},
                     store__sku="RFK_LEE_HO_KD_No_26/27")  # RFK kids kit with socks = shirt price
        self.assertNotIn(("Kho / Giá", "Giá"), groups(ok))
        nosock = product(site="CFS", store__prices={"price": "2969"}, store__sku="CFS_LEE_HO_KD_No_26/27",
                         store__name="Leeds United Home Kids Football Kit 2026/27 (No Socks)")
        self.assertIn(("Kho / Giá", "Giá"), groups(nosock))  # should be 26.69
        ls = product(store__prices={"price": "3399"}, store__sku="KFK_LEE_HOLV_KD_No_26/27",
                     store__name="Leeds United Home Kids Football Kit 2026/27 (With socks, Long Sleeve)")
        self.assertIn(("Kho / Giá", "Giá"), groups(ls))  # should be 30.99

    def test_template_fields_contradict_listing(self):
        d = product(store__description=product()["store"]["description"]
                    + "<h3>Kit Facts</h3><ul><li><strong>Kit:</strong> Away</li><li><strong>Sleeves:</strong> long</li>"
                      "<li><strong>In the parcel:</strong> 1 shirt and matching shorts. Socks are not included.</li></ul>")
        g = groups(d)
        self.assertIn(("Sai Home/Away/Third", "Description"), g)
        self.assertIn(("Sleeve", "Description"), g)
        self.assertIn(("Sai tất (socks)", "Description"), g)

    def test_option_label_names_other_kit(self):
        d = product(store__name="Leeds United Birthday Gift Pack – Home and Third Kids Football Kit 2026/27",
                    store__sku="KFK_LEE_HO/THGP_KD_No_26/27")
        d["page"]["options"] = ["Personalisation for Home shirt only £8", "Personalisation for Away shirt only £8"]
        self.assertIn(("Sai Home/Away/Third", "Option sản phẩm"), groups(d))

    def test_whole_page_contradictions(self):
        d = product(store__name="Leeds United Birthday Gift Pack – Home and Third Kids Football Kit 2026/27",
                    store__sku="KFK_LEE_HO/THGP_KD_No_26/27")
        d["page"]["body"] = ("Personalisation for Home shirt only £8\nPersonalisation for Away shirt only £8\n"
                             "“Ordered a Scotland away kit for my son”\nGermany\n9–13\nworking days\nPrice is jusst 47.99")
        g = groups(d)
        self.assertIn(("Sai Home/Away/Third", "Trang sản phẩm (option / tab / description)"), g)
        self.assertIn(("Lỗi chính tả", "Trang sản phẩm (option / tab / description)"), g)
        self.assertNotIn(("Sai team", "Trang sản phẩm (option / tab / description)"), g)  # review + delivery list

    def test_price_on_photo(self):
        d = product()
        d["page"]["image_price"] = [49.99]
        self.assertIn(("Kho / Giá", "Giá trên ảnh"), groups(d))
        d["page"]["image_price"] = [29.99]
        self.assertNotIn(("Kho / Giá", "Giá trên ảnh"), groups(d))

    def test_christmas_image_required_on_kfk(self):
        d = product()
        d["published_at"] = "2026-10-24 10:00"
        self.assertIn(("Christmas campaign", "Ảnh"), groups(d))
        d["store"]["images"].append({"alt": "Leeds xmas image", "src": "https://x/Leeds-Xmas-Gift-Gen-Image.webp"})
        self.assertNotIn(("Christmas campaign", "Ảnh"), groups(d))
        d["published_at"] = "2026-10-01 10:00"
        d["store"]["images"].pop()
        self.assertNotIn(("Christmas campaign", "Ảnh"), groups(d))

    def test_christmas_late_published_listing_judged_by_check_day(self):
        # KFK GORDON 17 (28/10): dated 26/10 but live only on 28/10, so the day's list has no publish date
        d = product()
        d["published_at"] = ""
        with mock.patch.object(x, "date") as fake:
            fake.today.return_value = date(2026, 10, 28)
            self.assertIn(("Christmas campaign", "Ảnh"), groups(d))
            fake.today.return_value = date(2027, 1, 5)
            self.assertNotIn(("Christmas campaign", "Ảnh"), groups(d))

    def test_catalog_data(self):
        d = product()
        d["store"]["attributes"] = [a for a in d["store"]["attributes"] if a["name"] != "Kit Option"]
        d["variations"] = [
            {"id": 11, "sku": "KFK_LEE_HO_KD_No_26/27_16", "attributes": [{"name": "Size", "value": "16-3-4-yrs"}]},
            {"id": 12, "sku": "", "attributes": [{"name": "Size", "value": "16-3-4-yrs"}]},
            {"id": 13, "sku": "KFK_LEE_AW_KD_No_26/27_20", "attributes": [{"name": "Size", "value": "20-5-6-yrs"}]},
        ]
        g = groups(d)
        self.assertIn(("Thiếu attribute", "Attribute Kit Option"), g)
        self.assertIn(("SKU", "SKU variation"), g)
        self.assertIn(("Variation", "Variation thiếu size"), g)  # 28 (12-13 yrs) has no variation
        self.assertIn(("Variation", "Attribute Size"), g)  # 20 (5-6 yrs) not in the attribute

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
