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


def base_groups(d):
    import qa_rules
    return sorted({(i["group"], i["field"]) for i in qa_rules.check_product(d)})


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

    REPORTED = {"teams": [
        {"label": "Bayern Munich (Adidas)", "team": "Bayern Munich", "scope": {"retro": False, "years": [], "seasons": []},
         "status": {"KFK": "Private (reported)", "CFS": "Published (blurred logo)"}},
        {"label": "Arsenal (Adidas)", "team": "Arsenal", "scope": {"retro": False, "years": [], "seasons": []},
         "status": {"KFK": "Published BUNDLE ONLY (blurred logo)", "RFK": "Published"}},
        {"label": "Retro Arsenal (Nike)", "team": "Arsenal", "scope": {"retro": True, "years": [], "seasons": []},
         "status": {"RFK": "Draft (reported)"}},
        {"label": "Liverpool 24/25 (Adidas & Nike)", "team": "Liverpool", "scope": {"retro": False, "years": [], "seasons": ["24/25"]},
         "status": {"RFK": "Draft (reported)"}},
        {"label": "Barcelona (Nike)", "team": "Barcelona", "scope": {"retro": False, "years": [], "seasons": []},
         "status": {"RFS": "Published / Private (reported)"}},
    ]}

    def reported(self, name, site="KFK"):
        d = product(store__name=name)
        d["site"] = site
        with mock.patch.object(x, "REPORTED", self.REPORTED):
            return [(i["severity"], i["field"]) for i in x.check_extra(d) if i["group"] == "Club bị report"]

    def test_reported_club_private(self):
        self.assertEqual(self.reported("Bay^_^rn Home Kids Football Kit 2026/27 (With socks)"), [(x.HIGH, "Trạng thái")])
        self.assertEqual(self.reported("Bayern Munich Home Kids Cheap Football Kit 2026/27", "CFS"), [(x.LOW, "Ảnh")])
        self.assertEqual(self.reported("Bayern Munich Home Kids Football Kit 2026/27", "RFS"), [])

    def test_reported_club_bundle_only(self):
        self.assertEqual(self.reported("North London Red Home Kids Football Kit 2026/27 (With Socks)"),
                         [(x.HIGH, "Trạng thái")])
        self.assertEqual(self.reported("North London Red Gift Pack – Home and Away Kids Football Kit 2026/27"), [])
        # 'Retro Arsenal' has no KFK status: a KFK retro single falls under the general Arsenal row
        self.assertEqual(self.reported("Retro North London Red Home Kids Football Kit 1990"), [(x.HIGH, "Trạng thái")])

    def test_reported_club_scopes(self):
        # 'Retro Arsenal' row only for retro; 'Liverpool 24/25' only for that season
        self.assertEqual(self.reported("Retro Arsn@l Away Kids Replica Football Kit 1988/1990", "RFK"),
                         [(x.HIGH, "Trạng thái")])
        self.assertEqual(self.reported("Arsn@l Home Kid Replica Football Kit 2026/27", "RFK"), [])
        self.assertEqual(self.reported("Liverpool Home Kid Replica Football Kit 2024/25", "RFK"), [(x.HIGH, "Trạng thái")])
        self.assertEqual(self.reported("Liverpool Home Kid Replica Football Kit 2025/26", "RFK"), [])

    def test_reported_club_mixed_status(self):
        self.assertEqual(self.reported("Barcelona Fourth Men Replica Football Shirt 2026/27", "RFS"), [(x.LOW, "Trạng thái")])

    def test_reported_sheet_import(self):
        import update_reported_clubs as u
        self.assertEqual(u.parse_label("Retro Portugal + Portugal 2024 + 2022 (Nike)"),
                         ("Portugal", "Nike", {"retro": True, "years": ["2024", "2022"], "seasons": []}))
        self.assertEqual(u.parse_label("Liverpool 24/25 (Adidas & Nike)")[0::2],
                         ("Liverpool", {"retro": False, "years": [], "seasons": ["24/25"]}))
        self.assertEqual(u.parse_label("Retro Man United (Nike)")[0], "Manchester United")

    def test_badge_template_line_is_not_a_word_to_avoid(self):
        for line in ("Badge options: Premier League sleeve badge can be added.",
                     "Adult’s Home kit badge options: Premier League sleeve badge can be added to both shirts.",
                     "Sleeve badge: Combo Chelsea 2025 badge can be added using the product options."):
            d = product()
            d["store"]["description"] += f"<p>{line}</p>"
            self.assertNotIn(("Words to Avoid", "Description"), base_groups(d), line)
        d = product()
        d["store"]["description"] += "<p>The club badge is stitched on the chest.</p>"
        self.assertIn(("Words to Avoid", "Description"), base_groups(d))

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



class SleeveBadge(unittest.TestCase):
    TM = ('<div class="tc-element-inner-wrap"><div class="tc-row">'
          '<h5 class="tc-cell tc-epo-label tm-epo-element-label tcwidth-100"> {label}</h5>'
          '<div class="tm-element-description"><p><img src="data:image/svg+xml;base64,AA" '
          'data-src="https://x/uploads/{img}" alt="{alt}"></p></div>'
          '<div class="tc-cell tc-col tc-element-container"><img src="https://x/other.png"></div></div></div>')

    def test_parse_badges(self):
        import qa_fetch
        page = self.TM.format(label='Add  Badge', img='Argentina-home-world-cup-2026-badge.webp', alt='')
        self.assertEqual(qa_fetch.parse_badges(page),
                         [{'label': 'Add Badge', 'images': ['Argentina-home-world-cup-2026-badge.webp']}])
        ppom = ('<input type="checkbox" data-optionid="add_premier_badge" data-label="Add Premier Badge" '
                'data-data_name="badge" value="Add Premier Badge">')
        self.assertEqual(qa_fetch.parse_badges(ppom), [{'label': 'Add Premier Badge', 'images': []}])

    def badge_issues(self, name, badges, site='KFK', desc=''):
        d = product()
        d['site'] = site
        d['store']['name'] = name
        d['page']['badges'] = badges
        issues = []
        x.check_sleeve_badge(d, lambda sev, group, field, detail, fix='': issues.append((sev, group, detail)),
                             name, desc)
        return issues

    def test_national_team_league_badge_is_high(self):
        issues = self.badge_issues('Qatar Home Cheap Football Shirts 2024', [{'label': 'Add Premier Badge', 'images': []}],
                                   site='CFS', desc='Sleeve badge: Premier League can be added using the product options.')
        self.assertEqual([(i[0], i[1]) for i in issues], [(x.HIGH, 'Sleeve badge')])

    def test_label_without_league_is_medium(self):
        issues = self.badge_issues('Al Nassr Home Men Replica Football Shirt 2026/27',
                                   [{'label': 'Add Sleeve Badge', 'images': ['Roshn_Saudi_League_Logo.png']}], site='RFS')
        self.assertEqual([i[0] for i in issues], [x.MED])

    def test_rfs_rfk_need_no_description_line(self):
        badge = [{'label': 'Adding Premier League Badge', 'images': []}]
        self.assertEqual(self.badge_issues('Chelsea Home Men Replica Football Shirt 2026/27', badge, site='RFK'), [])
        self.assertEqual([i[0] for i in self.badge_issues('Chelsea Home Kids Football Kit 2026/27', badge)], [x.MED])

    def test_old_cache_without_badges_is_skipped(self):
        d = product()
        issues = []
        x.check_sleeve_badge(d, lambda *a, **k: issues.append(a), d['store']['name'], '')
        self.assertEqual(issues, [])



class KitPartsWording(unittest.TestCase):
    def test_shirt_as_part_of_kit_is_fine(self):
        for line in ("What’s Included Long sleeve shirt with Messi name and number 10 already applied.",
                     "Name & number: The shirt is supplied without a name or number.",
                     "Player print: The shirt already has Gordon name and number 17 applied to the back."):
            d = product()
            d["store"]["description"] += f"<p>{line}</p>"
            self.assertNotIn(("Sai loại Shirt/Kit", "Description"), groups(d), line)
        d = product()
        d["store"]["description"] += "<p>A great shirt for young fans.</p>"
        self.assertIn(("Sai loại Shirt/Kit", "Description"), groups(d))


if __name__ == "__main__":
    unittest.main()
