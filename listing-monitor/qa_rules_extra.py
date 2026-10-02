"""Extra QA rules, added 2/10.

Part A comes from Clara's KFK QA checker (repo thuytran278/football-qa-tools,
KFK/kfk_rules.py: KFK Master File + Trademark Audit). Part B are new cases not
covered by either tool yet.

check_extra(data) returns issues in the same shape as qa_rules.check_product.
"""

import html
import re

from qa_rules import (HIGH, LOW, MED, attr, fold, fuzzy_contains, has_word, kits_in, parse_sku,
                      seasons_in, snippet, strip_html)

# ---------------------------------------------------------------- Part A: KFK master file rules

# Template bugs seen live (Trademark Audit). All sites.
TEMPLATE_BUGS = [
    (r"is this the real .{0,60}? kit design", "Xoá khối Q&A 'Is this the real ... kit design?' (hoặc đổi thành 'About this [Team] kit:')"),
    (r"\b(kit kit|shirt shirt|the the|and and)\b", "Lặp từ, xoá bớt 1 từ"),
    (r"%focuskw%|%title%|%page%|%sep%|%sitename%|%excerpt%", "Biến SEO chưa được thay, phải viết cụ thể"),
    (r"brand-style detail", "Placeholder lỗi do find/replace hàng loạt, viết lại tự nhiên"),
    (r"football-inspired football-inspired|inspired by the football-inspired", "Lặp 'football-inspired', sửa ngữ pháp"),
]

# Hard-banned on KFK only (RFS/RFK names legitimately say "Replica").
KFK_HARD_BANNED = r"official|authentic|identical|genuine|replica|louis vuitton|(?<![a-z])lv(?![a-z])"
REAL_CLUBS = r"real (madrid|betis|sociedad|oviedo|valladolid|mallorca|zaragoza|salt lake|sporting)"

# Extra words-to-avoid from the KFK reference table (not already in qa_rules). All sites.
EXTRA_AVOID = [
    (r"authenticity", "quality craftsmanship"),
    (r"same look and feel", "football-inspired look and comfortable feel"),
    (r"player versions?", "fan-style options"),
    (r"official store", "Football Kit Store"),
    (r"real or fake", "product quality"),
    (r"duplicate of the original", "inspired by classic football styles"),
    (r"replicas of the original", "designed with a familiar football-inspired look"),
    (r"air jordan|jordan brand|jordan training|x jordan", "brand detail"),
    (r"(etihad |emirates |qatar )?airways", "brand detail"),
    (r"mirror the real", "offer a familiar football-inspired style"),
]

OLD_COPY_SIGNS = ["buy now or cry later", "discount code everyday", "hottest price", "easily return within 30 days"]

GENERIC_NAME_WORDS = {
    'kids', 'kid', 'men', 'man', 'women', 'woman', 'football', 'kit', 'kits', 'shirt', 'shirts', 'home',
    'away', 'third', 'goalkeeper', 'pre', 'match', 'with', 'socks', 'sock', 'birthday', 'gift', 'pack',
    'bundle', 'retro', 'for', 'and', 'the', 'printed', 'world', 'cup', 'training', 'adult', 'baby', 'replica',
    'cheap', 'fan', 'version', 'edition', 'special', 'long', 'sleeve', 'set', 'full',
}

# Prices (KFK Master File section 9). Selling price, before printing/retro surcharges.
KFK_PRICE = {"kids_no_socks": 26.99, "kids_with_socks": 29.99, "adult_kit_no_socks": 30.99,
             "adult_kit_with_socks": 33.99, "shirt": 29.99}
KFK_BUNDLE_PRICE = {"kids_no_socks": 46.99, "kids_with_socks": 49.99, "men_shirt": 49.99, "printed": 64.99}

FREE_PIN_TEAMS = ['Spain', 'France', 'Argentina', 'England', 'Brazil', 'Portugal', 'Scotland']

# Reported Club Status sheet, KFK column (as in kfk_rules.py, 19 Jul 2026).
REPORTED_CLUBS_KFK = {
    'Barcelona': 'Published (blurred logo)', 'Brighton': 'Deleted (reported)',
    'Chelsea': 'Published (blurred logo)', 'England': 'Published (blurred logo)',
    'Liverpool': 'Published (blurred logo + change url)', 'Paris Saint-Germain': 'Private (reported)',
    'Tottenham Hotspur': 'Published (blurred logo)', 'Ajax': 'Private (reported)',
    'Arsenal': 'Published BUNDLE ONLY (blurred logo)', 'Aston Villa': 'Published (blurred logo)',
    'Bayern Munich': 'Private (reported)', 'Celtic': 'Private (reported)',
    'Manchester United': 'Draft (reported)', 'Newcastle': 'Draft (reported)',
    'Olympique Lyonnais': 'Private (reported)', 'Real Madrid': 'Published (blurred logo)',
    'Borussia Dortmund': 'Private (reported)', 'Bournemouth': 'Published (blurred logo)',
}
REPORTED_ALIASES = {
    'Paris Saint-Germain': ['psg', 'p^_^sg', 'paris saint germain'], 'Bayern Munich': ['bayern', 'bay^_^rn'],
    'Manchester United': ['man united', 'man^u^nited', 'manchester utd'], 'Liverpool': ['lvrp00l', 'lvr^_^pool'],
    'Arsenal': ['north london red', 'arsen^_^al', 'arsn@l'], 'Borussia Dortmund': ['dortmund', 'd0rt^_^mund'],
    'Olympique Lyonnais': ['lyon'], 'Newcastle': ['newcastle united'],
}

LEAGUE_CLUBS = {
    'Premier League': ['Arsenal', 'Aston Villa', 'Bournemouth', 'Brentford', 'Brighton', 'Burnley', 'Chelsea',
                       'Crystal Palace', 'Everton', 'Fulham', 'Ipswich Town', 'Leeds United', 'Leicester City',
                       'Liverpool', 'Manchester United', 'Manchester City', 'Newcastle', 'Nottingham Forest',
                       'Southampton', 'Sunderland', 'Tottenham Hotspur', 'Watford', 'West Bromwich', 'West Ham United',
                       'Wolves', 'Sheffield United', 'Luton'],
    'La Liga': ['Athletic Club', 'Atletico Madrid', 'Barcelona', 'Celta Vigo', 'Girona', 'Real Betis',
                'Real Madrid', 'Sevilla', 'Valencia', 'Villarreal', 'RCD Espanyol', 'Rayo Vallecano', 'Cadiz',
                'Granada', 'Malaga', 'UD Las Palmas'],
    'Serie A': ['AC Milan', 'Fiorentina', 'AS Roma', 'Bologna', 'Como 1907', 'Inter Milan', 'Juventus', 'Lazio',
                'Parma', 'SSC Napoli', 'Venezia'],
    'Bundesliga': ['Bayern Munich', 'Bayer Leverkusen', 'Borussia Dortmund', 'Eintracht Frankfurt',
                   'RB Leipzig', 'Wolfsburg', 'Werder Bremen', 'Borussia Mönchengladbach'],
    'Ligue 1': ['AS Monaco', 'FC Nantes', 'Lille', 'OGC Nice', 'Olympique Lyonnais', 'Olympique Marseille',
                'RC Lens', 'RC Strasbourg', 'Saint-Etienne', 'Toulouse'],
    'Eredivisie': ['Ajax', 'AZ Alkmaar', 'Feyenoord', 'PSV', 'Twente'],
    'Primeira Liga': ['Benfica', 'FC Porto', 'Sporting CP'],
}
WORLD_CUP_2026_TEAMS = ['Argentina', 'Australia', 'Austria', 'Belgium', 'Brazil', 'Canada', 'Colombia',
                        'Croatia', 'England', 'France', 'Germany', 'Japan', 'Korea', 'Mexico', 'Netherlands',
                        'Norway', 'Portugal', 'Scotland', 'Senegal', 'Spain', 'Switzerland', 'USA', 'Saudi Arabia',
                        'Egypt', 'Morocco', 'Ghana', 'Algeria', 'South Africa', 'Uruguay', 'Ecuador']

GENERIC_CATEGORY_TAG = re.compile(
    r"^best selling|gift packs?|^national teams?$|^players?$|popular players|league|^shop by|^world cup|^euro|"
    r"^bundesliga$|^la liga$|^serie a$|^ligue 1$|^primeira liga$|^eredivisie$|^championship$|^mls$|^retro|"
    r"^concept$|gift bundles?$|^kids? ?kits?$|^men'?s? shirts?$|^women'?s? shirts?$|^new|^sale$|^free country pin|"
    r"^gift for|^birthday gift|^personalised|^general$|^uncategori[sz]ed$|^featured$|^trending$|^clearance$|"
    r"^best sellers?$|^special offers?$|^budget|under £|^football clubs?$|^shop by type$|^goalkeeper|"
    r"^long sleeve|^fan version|^player version|^training|^special edition|^other clubs?$|primeira[- ]liga|"
    r"^eredivisie$|^mls|^saudi|^concept kits?$|^commemorative|^limited|^pre[- ]?match|^third kits?$|^away kits?$|"
    r"^home kits?$|^international|^efl$|^(south|north|central) america|^europe|^africa|^asia|^concacaf|^conmebol|"
    r"^uefa|^copa|^championship|^league one|^league two|^scottish|^spl$|^saudi pro|^club teams?$", re.I)


def tokens(text):
    return {w for w in re.findall(r"[a-z]+", fold(text)) if len(w) >= 3 and w not in GENERIC_NAME_WORDS}


def site_price(s):
    p = (s.get("prices") or {})
    rng = p.get("price_range") or {}
    raw = rng.get("min_amount") or p.get("price")
    try:
        return int(raw) / 10 ** int(p.get("currency_minor_unit", 2))
    except (TypeError, ValueError):
        return None


def check_extra(data):
    site, s, page = data["site"], data["store"], data.get("page", {})
    issues = []

    def add(sev, group, field, detail, fix=""):
        issues.append({"severity": sev, "group": group, "field": field, "detail": detail, "fix": fix})

    name = strip_html(s.get("name"))
    fname = fold(name)
    desc = strip_html(s.get("description"))
    short = strip_html(s.get("short_description"))
    seo_title, meta = page.get("seo_title", ""), page.get("meta_description", "")
    sku = parse_sku(s.get("sku"))
    is_gift = bool(sku and sku["gift"]) or has_word(fname, "gift", "bundle", "pack")
    is_retro = has_word(fname, "retro")
    cats = [html.unescape(c["name"]) for c in s.get("categories", [])]
    tags = [html.unescape(t["name"]) for t in s.get("tags", [])]
    team = (attr(s, "clubs name", "club name", "club", "clubs", "national team", "national teams", "team") or [""])[0]
    texts = [("Tên sản phẩm", name), ("Description", desc), ("Short description", short),
             ("SEO title", seo_title), ("Meta description", meta)]

    # ---------- A1. Template bugs (all sites)
    for field, text in texts:
        for rx, fix in TEMPLATE_BUGS:
            m = re.search(rx, text, re.I)
            if m:
                add(HIGH if field in ("Tên sản phẩm", "SEO title", "Meta description") else MED,
                    "Lỗi template / copy", field, f"'{m.group(0)}': " + snippet(text, re.escape(m.group(0)), 40), fix)

    # ---------- A2. Hard-banned words (KFK)
    if site == "KFK":
        for field, text in texts[:3]:
            hits = [m.group(0) for m in re.finditer(rf"(?<![a-z])({KFK_HARD_BANNED})(?![a-z])", text, re.I)]
            no_clubs = re.sub(REAL_CLUBS, "", text, flags=re.I)
            hits += [m.group(0) for m in re.finditer(r"(?<![a-z])real(?![a-z])", no_clubs, re.I)]
            if hits:
                add(HIGH, "Từ cấm tuyệt đối (KFK)", field,
                    "; ".join(f"'{h}' ({snippet(text, re.escape(h), 30)})" for h in dict.fromkeys(hits)),
                    "Xoá/thay (Master File 4.2: không dùng official, authentic, real, identical, genuine, replica)")

    # ---------- A3. Extra words to avoid (all sites)
    for field, text in texts:
        hits = [(m.group(0), fix) for rx, fix in EXTRA_AVOID for m in [re.search(rf"(?<![a-z]){rx}(?![a-z])", text, re.I)] if m]
        if hits:
            add(MED, "Words to Avoid", field, "; ".join(f"'{h}' ({snippet(text, re.escape(h), 30)})" for h, _ in hits),
                "; ".join(f"{h} -> {f}" for h, f in hits))

    # ---------- A4. Naming formula + forbidden characters (KFK)
    if site == "KFK" and not is_gift:
        miss = []
        if not has_word(fname, "football"):
            miss.append("thiếu chữ 'Football'")
        if not (has_word(fname, "shirt", "kit", "bodysuit", "tracksuit")):
            miss.append("thiếu 'Shirt' hoặc 'Kit'")
        if not re.search(r"\b(kids?|men|women|adult|baby)\b", fname):
            miss.append("thiếu đối tượng (Kids/Men/Women/Adult)")
        if not re.search(r"\b(19|20)\d{2}\b|\d{2}/\d{2}", name):
            miss.append("thiếu season/năm")
        if re.search(r"\bGK\b", name):
            miss.append("ghi 'GK', phải ghi 'Goalkeeper'")
        if miss:
            add(MED, "Tên sai công thức (KFK)", "Tên sản phẩm", "; ".join(miss),
                "[Club] [KitType] [Audience] Football [Shirt|Kit] [Season] (– PLAYER SỐ)")
    if site == "KFK" and re.search(r'[&"“”]', name):
        add(MED, "Tên sai công thức (KFK)", "Tên sản phẩm", f"Tên có ký tự cấm & hoặc \": {name}", "Đổi '&' thành 'and', bỏ dấu \"")

    # ---------- A5. SKU duplicate suffix -1/-2 (all sites)
    if re.search(r"-\d+$", s.get("sku") or ""):
        add(MED, "SKU", "SKU", f"SKU có đuôi '{s['sku'].rsplit('-', 1)[1]}' ({s['sku']}): dấu hiệu duplicate WooCommerce",
            "Bỏ đuôi -1/-2, kiểm tra có listing trùng không")

    # ---------- A6. Price (KFK) + Budget attribute (all sites)
    price = site_price(s)
    if site == "KFK" and sku and price:
        socks = "with" if "with socks" in fname else "no" if "no socks" in fname else None
        exp, aud = None, sku["audience"]
        if is_gift:
            if sku["player"] and len(re.findall(r"\d+", sku["player"])) > 1:
                exp = None  # 2 printed players: not in the Master File price table
            elif sku["player"]:
                exp = KFK_BUNDLE_PRICE["printed"]
            elif aud == "adult":
                exp = KFK_BUNDLE_PRICE["men_shirt"]
            elif socks:
                exp = KFK_BUNDLE_PRICE[f"kids_{socks}_socks"]
        else:
            if sku["aud_code"] == "KD" and socks and has_word(fname, "kit"):
                exp = KFK_PRICE[f"kids_{socks}_socks"]
            elif sku["aud_code"] == "ADK" and socks:
                exp = KFK_PRICE[f"adult_kit_{socks}_socks"]
            elif sku["aud_code"] in ("AD", "WM") and has_word(fname, "shirt"):
                exp = KFK_PRICE["shirt"]
            if exp:
                exp += (1 if is_retro else 0) + (10 if sku["player"] else 0) + (1 if sku["long_sleeve"] else 0)
        if exp and abs(price - exp) > 0.01:
            add(MED, "Kho / Giá", "Giá", f"Giá đang bán £{price:.2f}, bảng giá Master File là £{exp:.2f}",
                "Kiểm tra lại giá (Master File mục 9)")
    budget = attr(s, "budget")
    if budget and price:
        b = budget[0]
        m_under, m_over = re.search(r"under\s*£?\s*([\d.]+)", b, re.I), re.search(r"over\s*£?\s*([\d.]+)", b, re.I)
        m_rng = re.search(r"£?\s*([\d.]+)\s*[–-]\s*£?\s*([\d.]+)", b)
        ok = (price < float(m_under.group(1)) if m_under else price > float(m_over.group(1)) if m_over
              else float(m_rng.group(1)) <= price <= float(m_rng.group(2)) if m_rng else True)
        if not ok:
            add(MED, "Kho / Giá", "Attribute Budget", f"Budget '{b}' nhưng giá là £{price:.2f}", "Sửa attribute Budget")

    # ---------- A7. SEO title / meta must relate to the product (all sites)
    name_tok = tokens(name)
    for field, text in (("SEO title", seo_title), ("Meta description", meta)):
        if text and name_tok and not (name_tok & tokens(text)) and not fuzzy_contains(text, team or name.split()[0]):
            add(HIGH, "SEO", field, f"{field} không có từ khoá nào của sản phẩm: \"{text}\"",
                f"Viết lại {field} theo đúng sản phẩm (có thể còn từ template/listing khác)")
        for sign in OLD_COPY_SIGNS:
            if sign in text.lower():
                add(LOW, "SEO", field, f"Dùng copy cũ '{sign}'", "Thay bằng mẫu trust/gift hiện tại")
    if site == "KFK" and meta and len(meta) < 120:
        add(LOW, "SEO", "Meta description", f"Meta ngắn {len(meta)} ký tự (KFK: 140–160)", "Viết dài hơn")

    # ---------- A8. Free Pin promo (KFK)
    if site == "KFK" and "pin_text" in page:
        pin_team = next((t for t in FREE_PIN_TEAMS if has_word(fname, t.lower())), None)
        if pin_team and not page["pin_text"]:
            add(MED, "Khuyến mãi Free Pin (KFK)", "Trang sản phẩm",
                f"Sản phẩm {pin_team} (1 trong 7 đội có Free Pin) nhưng trang không có chữ 'FREE {pin_team.upper()} PIN'",
                "Kiểm tra BOGO coupon buy-" + pin_team.lower() + "-get-pin có gồm sản phẩm này không")

    # ---------- A9. Reported clubs (KFK)
    if site == "KFK":
        ident = " ".join([name, team])
        for club, status in REPORTED_CLUBS_KFK.items():
            names = [club.lower()] + REPORTED_ALIASES.get(club, [])
            fid = fold(ident)
            if any((n in fid) if len(n.replace("^", "").replace("_", "")) < 7 else fuzzy_contains(ident, n) for n in names):
                if not status.startswith("Published"):
                    add(HIGH, "Club bị report (KFK)", "Trạng thái",
                        f"{club}: sheet Reported Club Status ghi '{status}' nhưng listing đang live",
                        "Xem lại, chuyển Private/Draft theo sheet")
                elif "BUNDLE ONLY" in status and not is_gift:
                    add(HIGH, "Club bị report (KFK)", "Trạng thái",
                        f"{club}: chỉ được bán dạng bundle nhưng đây là listing lẻ", "Chuyển Private/Draft")
                else:
                    add(LOW, "Club bị report (KFK)", "Ảnh",
                        f"{club}: '{status}', nhớ kiểm tra logo đã blur trên ảnh", "Check blur logo")
                break

    # ---------- A10. Category taxonomy (KFK): parent league, National Team, World Cup 2026, Players
    if site == "KFK" and not is_retro:
        fc = [fold(c) for c in cats]
        missing = []
        if team:
            league = next((lg for lg, clubs in LEAGUE_CLUBS.items() if any(fuzzy_contains(team, c) for c in clubs)), None)
            # Only leagues that exist as KFK categories (no Eredivisie category on KFK).
            if league and league != "Eredivisie" and not any(fold(league) == c for c in fc):
                missing.append(f"'{league}' (league của {team})")
            if team in WORLD_CUP_2026_TEAMS or any(fold(team) == fold(t) for t in WORLD_CUP_2026_TEAMS):
                if not any(c.startswith("national team") for c in fc):
                    missing.append("'National Team'")
                if "2026" in name and "world cup" in fname and "world cup 2026" not in fc:
                    missing.append("'World Cup 2026'")
        if sku and sku["player"] and not re.fullmatch(r"(winners|champions)\s*\d*", fold(sku["player"])):
            if "players" not in fc and "popular players" not in fc:
                missing.append("'Players' (category cha của cầu thủ)")
            num = re.search(r"\d+", sku["player"])
            sur = re.split(r"[\s.'’-]", sku["player"].split()[0] if " " in sku["player"] else sku["player"])[-1]
            cand = [c for c in cats if fold(sur) and fold(sur) in fold(c)]
            if cand and num and not any(re.search(rf"\b{num.group(0)}\b", c) for c in cand):
                missing.append(f"số áo không khớp: tên '{sku['player']}' nhưng category '{cand[0]}'")
        if missing:
            add(MED, "Category / Tag", "Category", "Thiếu/sai category: " + ", ".join(missing), "Thêm category đúng taxonomy KFK")

    # ---------- A11. Tag/category from another team or season (all sites)
    name_seasons = seasons_in(name)
    title_tok = tokens(name) | tokens(team)
    for kind, items in (("Category", cats), ("Tag", tags)):
        for item in items:
            if GENERIC_CATEGORY_TAG.search(item.strip()):
                continue
            it = tokens(re.sub(r"(?i)^retro\s+", "", item))
            if it and not (it & title_tok) and not fuzzy_contains(name + " " + team, item.split(" ")[0]) and not is_gift:
                add(MED, "Category / Tag", kind, f"{kind} '{item}' không liên quan tới tên sản phẩm (copy từ listing khác?)",
                    f"Xoá/sửa {kind.lower()}")
            other = seasons_in(item) - name_seasons
            if name_seasons and other and (it & title_tok) and not is_retro:
                add(MED, "Sai season", kind, f"{kind} '{item}' ghi season {', '.join(other)} nhưng tên là {next(iter(name_seasons))}",
                    f"Đổi sang {kind.lower()} season đúng")

    # ---------- A12. Short description kit words vs title (all sites)
    sk = kits_in(short) - {"training"}
    nk = kits_in(name)
    if sk and nk and not is_gift and sk - nk:
        add(MED, "Sai Home/Away/Third", "Short description",
            f"Short description ghi {'/'.join(sorted(sk - nk))} nhưng tên là {'/'.join(sorted(nk))}: "
            + snippet(short, "|".join("goalkeeper|gk" if x == "gk" else x for x in sk - nk)), "Sửa short description")

    # ---------- A13. Description type consistency (KFK): Kit listing must not say shirt, and vice versa
    if site == "KFK" and not is_gift:
        is_kit, is_shirt = has_word(fname, "kit"), has_word(fname, "shirt")
        bad = "shirt" if is_kit and not is_shirt else "kit" if is_shirt and not is_kit else None
        if bad:
            clean = re.sub(r"(?i)kid'?s'? kit size chart|men'?s'? shirt size chart|women'?s'? shirt size chart|"
                           r"adult kit size chart|shirt length \(cm\)|shorts length \(cm\)|shirts (and|&) kits", "", desc)
            hits = list(re.finditer(rf"\b{bad}s?\b", clean, re.I))
            if hits:
                add(MED, "Sai loại Shirt/Kit", "Description",
                    f"Listing là {'KIT' if bad == 'shirt' else 'SHIRT'} nhưng description dùng chữ '{bad}' {len(hits)} lần: "
                    + snippet(clean, rf"\b{bad}s?\b", 40), "Master File 4: kit không ghi 'shirt' và ngược lại")

    # ---------------------------------------------------------- Part B: new cases

    # B1. Title typos: double spaces, misspelt socks marker, odd kit words
    if "  " in s.get("name", ""):
        add(LOW, "Lỗi chính tả", "Tên sản phẩm", "Tên có 2 dấu cách liền nhau", "Xoá bớt dấu cách")
    for paren in re.findall(r"\(([^)]*)\)", name):
        for part in (x.strip() for x in paren.split(",")):
            if re.search(r"s\w?o\w?c?k|so[ck]s", part, re.I) and not re.fullmatch(r"(with|no) socks", part, re.I):
                add(HIGH, "Lỗi chính tả", "Tên sản phẩm", f"Sai chính tả phần socks: '({paren})'",
                    "Sửa thành '(With Socks)' hoặc '(No Socks)'")
    m = re.search(r"\b(third way|hom|awy|thrid|socsk|footbal|shrit|kits kit)\b", fname)
    if m:
        add(HIGH, "Lỗi chính tả", "Tên sản phẩm", f"Có thể sai chính tả: '{m.group(0)}' trong \"{name}\"", "Sửa tên")

    # B2. Slug: old season / other kit type in the URL
    slug = (s.get("permalink") or "").rstrip("/").rsplit("/", 1)[-1]
    slug_txt = slug.replace("-", " ")
    if name_seasons and not is_retro:
        other = seasons_in(re.sub(r"(\d{4}) (\d{2})", r"\1/\2", slug_txt)) - name_seasons
        if other:
            add(MED, "URL / Slug", "Slug", f"Slug có season {', '.join(other)} nhưng tên là {next(iter(name_seasons))}: /{slug}/",
                "Đổi slug (nhớ tạo redirect 301 nếu listing đã có traffic)")
    sk_slug = kits_in(slug_txt) - {"training"}
    if nk and sk_slug and not (sk_slug & nk) and not is_gift:
        add(MED, "URL / Slug", "Slug", f"Slug ghi {'/'.join(sorted(sk_slug))} nhưng tên là {'/'.join(sorted(nk))}: /{slug}/",
            "Đổi slug cho đúng loại áo")
    tail = re.search(r"-(\d{1,2})$", slug)
    if tail and not re.search(r"(19|20)\d{2}-\d{1,2}$", slug) and not re.search(rf"\b{tail.group(1)}\b", name):
        add(LOW, "URL / Slug", "Slug", f"Slug có đuôi số (-{tail.group(1)}): có thể là bản duplicate", "Kiểm tra listing trùng")

    # B3. Prices: sale >= regular, or regular missing
    p = s.get("prices") or {}
    try:
        reg, sale = int(p.get("regular_price") or 0), int(p.get("sale_price") or 0)
        if reg and sale and sale > reg:
            add(MED, "Kho / Giá", "Giá", f"Giá sale (£{sale / 100:.2f}) cao hơn giá gốc (£{reg / 100:.2f})", "Sửa giá")
    except ValueError:
        pass

    # B4. Thin content
    if len(desc.split()) < 60:
        add(MED, "Nội dung", "Description", f"Description quá ngắn ({len(desc.split())} từ)", "Viết đủ description theo template site")
    if not short:
        add(MED, "Nội dung", "Short description", "Thiếu short description", "Thêm short description")

    # B5. Size chart image present (all sites, not gift/accessory)
    imgs = " ".join(fold((i.get("alt") or "") + " " + (i.get("src") or "")) for i in s.get("images", []))
    if s.get("images") and "size" not in imgs and not is_gift and not re.search(r"size\s*(chart|guide)", desc, re.I):
        add(MED, "Ảnh", "Size chart", "Không thấy ảnh size chart (gallery) hoặc bảng size trong description",
            "Thêm size chart đúng đối tượng")

    # B6. Main image broken (checked at fetch time)
    if page.get("main_image_ok") is False:
        add(HIGH, "Ảnh", "Ảnh chính", f"Ảnh chính không tải được: {s['images'][0].get('src', '')}", "Upload lại ảnh chính")

    return issues


def check_extra_batch(products):
    """Duplicate product names on the same site (TC 029)."""
    seen = {}
    for d in products:
        seen.setdefault((d["site"], fold(strip_html(d["store"]["name"]))), []).append(d)
    out = []
    for (_, _), ds in seen.items():
        if len(ds) > 1:
            ids = ", ".join(str(x["store"]["id"]) for x in ds)
            for d in ds:
                out.append((d, {"severity": MED, "group": "Trùng lặp", "field": "Tên sản phẩm",
                                "detail": f"Trùng tên với listing khác ({ids})", "fix": "Kiểm tra listing trùng, giữ 1 bản"}))
    return out
