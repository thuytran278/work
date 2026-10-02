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

    def test_duplicate_names(self):
        a, b = product(), copy.deepcopy(product())
        b["store"]["id"] = 2
        self.assertEqual(len(x.check_extra_batch([a, b])), 2)


if __name__ == "__main__":
    unittest.main()
