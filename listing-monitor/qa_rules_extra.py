"""Extra QA rules, added 2/10.

Part A comes from Clara's KFK QA checker (repo thuytran278/football-qa-tools,
KFK/kfk_rules.py: KFK Master File + Trademark Audit). Part B are new cases not
covered by either tool yet.

check_extra(data) returns issues in the same shape as qa_rules.check_product.
"""

import html
import json
import re
from collections import Counter
from pathlib import Path

from qa_rules import (HIGH, LOW, MED, TEAM_ALIASES, YEAR_RE, attr, fold, fuzzy_contains, has_word, kits_in, parse_sku,
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

# Prices (Clara 22/10). Shirt price per site; kids kit with socks = shirt price; no socks is cheaper
# (KFK/CFS -3, RFS/RFK -2, as on the live sites); printed +10, long sleeve +1, retro +1 (both: +2).
SHIRT_PRICE = {"KFK": 29.99, "RFS": 27.99, "RFK": 27.49, "CFS": 29.69}
NO_SOCKS_DISCOUNT = {"KFK": 3, "RFS": 2, "RFK": 2, "CFS": 3}
# Adult kits (ADK) with socks, as on the live sites (confirmed by Clara 22/10)
ADULT_KIT_WITH_SOCKS = {"KFK": 33.99, "CFS": 33.69}

# Gift packs and anything without a fixed rule: compare with the price most listings of the same kind have live
# (Clara 22/10: "follow what is on live"). Rebuilt from the cache on every QA run, saved in data/price_ref.json.
PRICE_REF_PATH = Path(__file__).resolve().parent / "data" / "price_ref.json"


def price_key(s, name):
    sku = parse_sku(s.get("sku"))
    if not sku:
        return None
    fname = fold(name)
    kind = "gift" if sku["gift"] or has_word(fname, "gift", "bundle", "pack") else "kit" if has_word(fname, "kit") else "shirt"
    players = len(re.findall(r"\d+", sku["player"] or ""))
    return "|".join([kind, sku["aud_code"].upper(), kit_socks(s, name) or "-", str(players),
                     "LS" if sku["long_sleeve"] or re.search(r"long[\s-]sleeve", name, re.I) else "-",
                     "R" if has_word(fname, "retro") else "-"])


def build_price_ref(products):
    """{site: {key: [mode price, listings, share]}} from cached products (data dicts)."""
    groups = {}
    for d in products:
        s = d.get("store") or {}
        price, key = site_price(s), price_key(s, strip_html(s.get("name")))
        if price and key:
            groups.setdefault(d["site"], {}).setdefault(key, Counter())[price] += 1
    return {site: {k: [c.most_common(1)[0][0], sum(c.values()), round(c.most_common(1)[0][1] / sum(c.values()), 2)]
                   for k, c in keys.items()} for site, keys in groups.items()}


def load_price_ref():
    try:
        return json.loads(PRICE_REF_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


PRICE_REF = load_price_ref()

try:
    CAMPAIGNS = json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8")).get(
        "christmas_campaign", {})
except (OSError, ValueError):
    CAMPAIGNS = {}
XMAS_RE = re.compile(r"x-?mas|christmas|santa|festive", re.I)

# Colour make-up of every listing's main photo, all sites (data/image_fp.json, rebuilt from the cache on each QA run).
# A "Home" listing whose photo matches the team's Away kit (on any site) better than its Home kit = wrong photos.
IMAGE_FP_PATH = Path(__file__).resolve().parent / "data" / "image_fp.json"


def photo_key(s, name):
    """(team, season, kit) for single-kit, non-gift listings; None when the photo is not comparable."""
    fname = fold(name)
    sku = parse_sku(s.get("sku"))
    if (sku and sku["gift"]) or has_word(fname, "gift", "bundle", "pack", "set", "training", "pre", "special", "edition",
                                          "commemorative", "anniversary", "concept", "goalkeeper", "gk"):
        return None
    kits = kits_in(name) - {"training"}
    team = (attr(s, "clubs name", "club name", "club", "clubs", "national team", "national teams", "team") or [""])[0]
    seasons = sorted(seasons_in(name) | set(YEAR_RE.findall(name)))
    if len(kits) != 1 or not team or not seasons:
        return None
    t = fold(team)
    for real, aliases in TEAM_ALIASES.items():
        if t in aliases:
            t = real
    return [t, seasons[0], next(iter(kits)), "retro" if has_word(fname, "retro") else "new"]


def load_image_fp():
    try:
        return json.loads(IMAGE_FP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


IMAGE_FP = load_image_fp()


def colour_sim(a, b):
    return sum(min(x, y) for x, y in zip(a, b))

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


def kit_socks(s, name):
    """'with' / 'no' / None, from the name first, then the Kit Option attribute."""
    for text in (name, " ".join(attr(s, "kit option"))):
        if re.search(r"\bno[\s-]socks?\b|without socks", text, re.I):
            return "no"
        if re.search(r"\bwith socks?\b", text, re.I):
            return "with"
    return None


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

    # ---------- A6. Price (all sites) + Budget attribute
    price = site_price(s)
    if sku and price:
        socks = kit_socks(s, name)
        exp, sev, aud = None, HIGH, sku["audience"]
        if is_gift:
            ref = PRICE_REF.get(site, {}).get(price_key(s, name) or "")
            if ref and ref[1] >= 3 and ref[2] >= 0.6 and abs(price - ref[0]) > 0.01:
                add(MED, "Kho / Giá", "Giá", f"Giá đang bán £{price:.2f}, trong khi {ref[1]} gift pack cùng loại đang live "
                    f"phần lớn ({int(ref[2] * 100)}%) là £{ref[0]:.2f}", "Kiểm tra lại giá gift pack")
        elif site in SHIRT_PRICE:
            base = SHIRT_PRICE[site]
            if sku["aud_code"] == "KD" and has_word(fname, "kit") and socks:
                exp = base - (NO_SOCKS_DISCOUNT[site] if socks == "no" else 0)
            elif sku["aud_code"] == "ADK" and socks and site in ADULT_KIT_WITH_SOCKS:
                exp = ADULT_KIT_WITH_SOCKS[site] - (NO_SOCKS_DISCOUNT[site] if socks == "no" else 0)
            elif sku["aud_code"] in ("AD", "WM") and has_word(fname, "shirt"):
                exp = base
            if exp:
                exp += ((1 if is_retro else 0) + (10 if sku["player"] else 0)
                        + (1 if sku["long_sleeve"] or re.search(r"long[\s-]sleeve", name, re.I) else 0))
        if exp and abs(price - exp) > 0.01:
            parts = ["giá gốc"] + [w for w, on in (("no socks", socks == "no"), ("in sẵn +10", sku["player"]),
                                                   ("long sleeve +1", sku["long_sleeve"]), ("retro +1", is_retro)) if on]
            add(sev, "Kho / Giá", "Giá", f"Giá đang bán £{price:.2f}, đúng ra là £{exp:.2f} ({', '.join(parts)})",
                "Sửa giá tất cả variation theo bảng giá")
        rng = (s.get("prices") or {}).get("price_range") or {}
        if rng.get("min_amount") and rng.get("max_amount") and rng["min_amount"] != rng["max_amount"] and not is_gift:
            add(MED, "Kho / Giá", "Variation", f"Các size có giá khác nhau (£{int(rng['min_amount']) / 100:.2f} – "
                f"£{int(rng['max_amount']) / 100:.2f})", "Đặt cùng 1 giá cho mọi size")
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
            # New KFK template (Oct 2026) lists the kit's parts: "Football shirt with ... / Matching shorts", "applied to
            # the shirt", "Long Sleeve shirt, matching shorts": the shirt as a part of the kit is not a type error.
            clean = re.sub(r"(?i)(?:football |short[\s-]sleeve |long[\s-]sleeve )?shirts?(?=[^.]{0,60}\bshorts\b)|"
                           r"(?:applied|printed) (?:to|on) the (?:back of the )?shirt|football shirt with", "", clean)
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

    check_extra_c(data, add, name, desc, short, meta, sku, is_gift, team)
    check_player_seo(data, add, name, seo_title, sku, is_gift)
    check_template_fields(data, add, name, sku, is_gift)
    check_campaign_and_photo_price(data, add, name, site, is_gift)
    check_photo_kit(data, add, name)
    if (data.get("page") or {}).get("body"):
        check_page_body(data, add, name, sku, is_gift, is_retro, team)
    else:
        check_page_options(data, add, name)
    return issues


# ---------------------------------------------------------------- Part C: football-qa-tools commit c3c1e3c (2/10)

# Goalkeeper first: "Goalkeeper Home" names a goalkeeper kit, not the outfield home kit.
KIT_SIDE = [("goalkeeper", r"\b(goalkeeper|gk)\b"), ("home", r"\bhome\b"), ("away", r"\baway\b"), ("third", r"\bthird\b")]
CAT_KIT = KIT_SIDE + [("training", r"\btraining\b"), ("pre-match", r"\bpre[\s-]?match\b")]
KIT_COLOURS = ['purple', 'pink', 'green', 'yellow', 'red', 'blue', 'orange', 'navy', 'burgundy', 'maroon', 'teal',
               'gold', 'silver', 'brown', 'cream', 'violet', 'lime', 'turquoise', 'rose', 'coral', 'cyan', 'indigo',
               'black', 'white', 'grey', 'gray']
NEUTRAL = {'black', 'white', 'grey', 'gray'}
EXTRA_ENTITIES = ['Celtic', 'Rangers', 'Boca Juniors', 'River Plate', 'Inter Miami', 'Al Nassr', 'Al Hilal',
                  'Al Ittihad', 'Galatasaray', 'Fenerbahce', 'Besiktas', 'Benfica', 'FC Porto', 'Sporting CP', 'Ajax',
                  'PSV', 'Feyenoord', 'Flamengo', 'Santos', 'Palmeiras', 'Corinthians', 'Club America', 'LA Galaxy',
                  'Wrexham', 'Middlesbrough', 'Stoke City', 'Derby County', 'Coventry City', 'Bolton', 'Portsmouth',
                  'Real Oviedo', 'Schalke', 'Norway', 'Italy', 'Wales', 'Ireland', 'Northern Ireland', 'Denmark',
                  'Sweden', 'Poland', 'Ukraine', 'Nigeria', 'Jamaica', 'Chile', 'Peru']
ADULT_SIZE = re.compile(r"^(XXS|XS|S|M|L|XL|XXL|2XL|3XL|XXXL|4XL|XXXXL|5XL|XXXXXL)$", re.I)
SIZE_NORM = {'2XL': 'XXL', 'XXXL': '3XL', 'XXXXL': '4XL', 'XXXXXL': '5XL'}
STANDARD_IMG = re.compile(r"size.?chart|size.?guide|delivery|infographic|inforgraphic|review|faq|background", re.I)


def kit_side(text):
    return next((k for k, rx in KIT_SIDE if re.search(rx, text or "", re.I)), None)


def cat_kit(text):
    return next((k for k, rx in CAT_KIT if re.search(rx, text or "", re.I)), None)


def colours(text):
    return {c for c in KIT_COLOURS if re.search(rf"\b{c}\b", text or "", re.I)}


def entities():
    names = [c for clubs in LEAGUE_CLUBS.values() for c in clubs] + WORLD_CUP_2026_TEAMS + EXTRA_ENTITIES
    return sorted(set(names), key=len, reverse=True)


ENTITIES = entities()


def check_extra_c(data, add, name, desc, short, meta, sku, is_gift, team):
    s = data["store"]
    raw_desc = s.get("description") or ""
    fname = fold(name)
    imgs = [(i.get("src") or "", strip_html(i.get("alt"))) for i in s.get("images", [])]
    pimgs = [(src, alt) for src, alt in imgs if not STANDARD_IMG.search(src + " " + alt)]

    def fname_text(src):
        return re.sub(r"[-_]", " ", src.rstrip("/").rsplit("/", 1)[-1].rsplit(".", 1)[0])

    # C1. Price written in the description must match the selling price (within 30%: same ballpark)
    p = s.get("prices") or {}
    try:
        page_price = int(p.get("sale_price") or p.get("price")) / 100
    except (TypeError, ValueError):
        page_price = None
    if page_price and page_price >= 1:
        bad = []
        for m in re.finditer(r"£\s*(\d{1,5}(?:[.,]\d{2})?)|(\d{1,5}(?:[.,]\d{2})?)\s*GBP", desc + " " + short, re.I):
            found = float((m.group(1) or m.group(2)).replace(",", "."))
            if abs(found - page_price) / page_price <= 0.30 and abs(found - page_price) > 0.02:
                bad.append(m.group(0))
        if bad:
            add(HIGH, "Kho / Giá", "Description",
                f"Description ghi giá {', '.join(dict.fromkeys(bad))} nhưng giá đang bán là £{page_price:.2f}: "
                + snippet(desc + " " + short, re.escape(bad[0]), 50), "Sửa giá trong description cho khớp")

    # C2. "Main colours" field + C3. colours in image alt/filename vs description
    if not is_gift and site_has_main_colours(data["site"]):
        if not re.search(r"main\s+colou?rs?", desc, re.I):
            add(LOW, "Nội dung", "Description", "Thiếu dòng 'Main colours' trong Product Details",
                "Thêm 'Main colours: [màu] shirt; [màu] shorts' theo template")
    desc_primary = colours(desc) - NEUTRAL
    if desc_primary and not is_gift:
        bad = []
        for src, alt in pimgs:
            if not alt:
                continue
            img_c = (colours(alt) | colours(fname_text(src))) - NEUTRAL
            if img_c and not (img_c & desc_primary):
                bad.append(f"\"{alt[:60]}\" ghi {'/'.join(sorted(img_c))}")
        if bad:
            add(MED, "Ảnh", "Màu ảnh vs description",
                f"Description ghi màu {'/'.join(sorted(desc_primary))} nhưng ảnh: " + "; ".join(bad[:3]),
                "Kiểm tra ảnh hoặc màu trong description (sai ảnh hoặc sai copy)")

    # C4. Size table in description lists sizes that cannot be bought
    var_sizes = {SIZE_NORM.get(t.upper().replace(" ", ""), t.upper().replace(" ", "")) for t in attr(s, "size", "sizes")}
    if var_sizes and all(ADULT_SIZE.match(v) for v in var_sizes):
        table_sizes = set()
        for tbl in re.findall(r"<table.*?</table>", raw_desc, re.S | re.I):
            for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tbl, re.S | re.I):
                c = strip_html(cell).upper().replace(" ", "")
                if ADULT_SIZE.match(c):
                    table_sizes.add(SIZE_NORM.get(c, c))
        extra = table_sizes - var_sizes
        if extra:
            add(MED, "Sai đối tượng", "Bảng size",
                f"Bảng size trong description có {sorted(extra)} nhưng không mua được (size đang bán: {sorted(var_sizes)})",
                "Bỏ dòng size không bán khỏi bảng, hoặc thêm variation")

    # C5. "(No socks)" title vs "complete kit / includes socks" in description or meta
    if re.search(r"\bno[\s-]socks?\b", name, re.I):
        rx = r"\b(complete\s+(?:\w+\s+){0,4}kit\s+included|includes?\s+socks?|socks?\s+(are\s+)?included)\b"
        where = [f for f, t in (("Meta description", meta), ("Description", desc + " " + short)) if re.search(rx, t, re.I)]
        if where:
            add(HIGH, "Sai tất (socks)", where[0],
                f"Tên ghi (No socks) nhưng {' và '.join(where)} ghi có tất/complete kit: "
                + snippet(meta if where[0] == "Meta description" else desc + " " + short, rx, 40),
                "Sửa câu bị copy từ template With Socks")

    # C6. Images naming another club/team, C7. image kit side vs title (alt + filename)
    title_ident = name + " " + team
    tks = kit_side(name)
    wrong_team, wrong_side = [], []
    for src, alt in pimgs:
        ft = fname_text(src)
        for label, text in (("alt", alt), ("file", ft)):
            if not text:
                continue
            others = [e for e in ENTITIES if re.search(rf"\b{re.escape(e)}\b", text, re.I)
                      and not re.search(rf"\b{re.escape(e)}\b", title_ident, re.I) and not fuzzy_contains(title_ident, e)]
            if others:
                wrong_team.append(f"{label} \"{text[:60]}\" → {others[0]}")
            ks = kit_side(text)
            sides = {k for k, rx in KIT_SIDE if re.search(rx, text, re.I)}
            if tks and ks and tks not in sides and not is_gift:
                wrong_side.append(f"{label} \"{text[:60]}\" ghi {ks}")
    if wrong_team and not is_gift:
        add(HIGH, "Ảnh", "Ảnh sai team", "Ảnh mang tên team khác: " + "; ".join(dict.fromkeys(wrong_team[:3])),
            "Kiểm tra có upload nhầm ảnh team khác không")
    if wrong_side:
        add(HIGH, "Sai Home/Away/Third", "Ảnh (alt/tên file)",
            f"Tên là {tks} nhưng ảnh: " + "; ".join(dict.fromkeys(wrong_side[:3])), "Kiểm tra có upload nhầm ảnh không")

    # C8. Kids photos on a men's listing and vice versa
    if sku and not is_gift:
        aud = sku["audience"]
        bad, in_alt = [], False
        for src, alt in pimgs:
            for text in (alt, fname_text(src)):
                if (aud == "adult" and re.search(r"\b(kids?|children|child|boys?|girls?|junior|youth)\b", text, re.I)
                        or aud == "kids" and re.search(r"\bmen'?s?\b|\badult\b", text, re.I)):
                    bad.append(text[:60])
                    in_alt = in_alt or text == alt
        if bad:
            # file name only: often a photo reused from the other audience's listing, so check rather than alarm
            add(HIGH if in_alt else MED, "Sai đối tượng", "Ảnh (alt/tên file)",
                f"Listing {'Men/Adult' if aud == 'adult' else 'Kids'} nhưng ảnh ghi: \"{bad[0]}\"",
                "Kiểm tra có upload nhầm bộ ảnh của đối tượng khác không")

    # C9. Fewer than 3 product photos
    distinct = {re.sub(r"-\d+x\d+(\.[^./?]+)$", r"\1", src) for src, _ in pimgs}
    if s.get("images") and len(distinct) < 3:
        add(LOW, "Ảnh", "Số lượng ảnh", f"Chỉ có {len(distinct)} ảnh sản phẩm (nên ≥ 3: trước / sau / chi tiết)", "Thêm ảnh")

    # C10. Category of another kit type
    tck = cat_kit(name)
    if tck and not is_gift:
        wrong = [c["name"] for c in s.get("categories", []) if cat_kit(c["name"]) not in (None, tck)]
        if wrong:
            add(MED, "Category / Tag", "Category", f"Tên là {tck} nhưng có category {', '.join(html.unescape(w) for w in wrong)}",
                "Xoá category sai loại áo (còn sót từ listing khác)")

    # C11. Players attribute vs SKU print segment
    players = attr(s, "players", "player")
    if sku and sku["player"] and players:
        if not any(fuzzy_contains(pl, sku["player"].split()[0]) for pl in players):
            add(LOW, "Sai cầu thủ", "Attribute Players", f"SKU in '{sku['player']}' nhưng attribute Players = {', '.join(players)}",
                "Kiểm tra lại cho khớp")

    # C12. Copy errors: doubled words, 3+ same letters in a row
    errs = []
    # Keep tag boundaries: "About Brazil</h3><p>Brazil is..." is a heading + sentence, not a doubled word.
    def sep(h):
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", h or "")))
    for field, text in (("Description", sep(raw_desc)), ("Short description", sep(s.get("short_description")))):
        for m in re.finditer(r"\b([a-zA-Z]{2,})\s+\1\b", text, re.I):
            errs.append((field, f"lặp '{m.group(0)}'", m.group(0)))
        for m in re.finditer(r"\b[a-zA-Z]*([a-zA-Z])\1{2,}[a-zA-Z]*\b", text):
            if not re.fullmatch(r"(x{2,4}l|www)", m.group(0), re.I):
                errs.append((field, f"'{m.group(0)}' (3 chữ liền)", m.group(0)))
    if errs:
        f0 = errs[0]
        add(MED, "Lỗi chính tả", f0[0], "; ".join(dict.fromkeys(e[1] for e in errs[:4])) + ": "
            + snippet(desc + " " + short, re.escape(f0[2]), 30), "Sửa lỗi đánh máy")

    # C13. SKU with spaces / non-ASCII (Google Merchant rejects them)
    raw_sku = s.get("sku") or ""
    if re.search(r"\s", raw_sku) or re.search(r"[^\x20-\x7E]", raw_sku):
        add(LOW, "SKU", "SKU (Google)", f"SKU '{raw_sku}' có dấu cách hoặc ký tự đặc biệt: Google Merchant không nhận",
            "Dùng chữ không dấu, số, - hoặc _ (vd FERRAN-9)")

    # C14. Size chart heading in description for another audience
    if sku and sku["audience"] and not is_gift:
        exp = {"kids": "kids", "adult": "men", "women": "women", "baby": None}.get(sku["audience"])
        found = set()
        dl = desc.lower()
        for m in re.finditer(r"size\s*(?:chart|guide)", dl):
            w = dl[max(0, m.start() - 60):m.start()]
            found.add("kids" if re.search(r"\bkid", w) else "women" if re.search(r"\bwomen", w)
                      else "men" if re.search(r"\b(men|adult)\b", w) else None)
        found.discard(None)
        if exp and found and exp not in found:
            add(HIGH, "Sai đối tượng", "Size chart (description)",
                f"Description có size chart {'/'.join(sorted(found))} nhưng listing là {exp}", "Đổi size chart đúng đối tượng")

    # C15. Multi-value attributes: every value must appear in the title
    for a in s.get("attributes", []):
        if fold(a["name"]) in ("clubs name", "club name", "national team", "national teams", "players") and len(a.get("terms", [])) > 1:
            bad = [html.unescape(t["name"]) for t in a["terms"]
                   if not fuzzy_contains(name, html.unescape(t["name"]).split(" ")[0])]
            if bad and not is_gift:
                add(MED, "Category / Tag", f"Attribute {a['name']}", f"Attribute {a['name']} có {', '.join(bad)} không có trong tên",
                    "Xoá giá trị attribute thừa")


def site_has_main_colours(site):
    # "Main colours" is part of the KFK description template (Product Details).
    return site == "KFK"


# ---------------------------------------------------------------- Part D: SEO case CFS player listings (2/10)
# Traffic on CFS fell ~75% around 20/8/2026, the same week 107 near-duplicate player listings went live.
# Agreed format (Clara, 2/10): player name right after the club, never as a "– PLAYER 9" suffix.
#   Name: [Club] [PLAYER] [No.] [Home/Away/Third] [Men/Kids] Cheap Football [Shirt/Kit] [Season]
#   H1:   [Club] [PLAYER] [No.] [Home/Away/Third] [Men/Kids] [Shirt/Kit] [Season]
#   Slug: unchanged.
PLAYER_SUFFIX = re.compile(r"\s[–-]\s*([A-ZÀ-ÝØ][A-ZÀ-ÝØ.'’\- ]+\s\d{1,2})\s*(\((with|no) socks\))?\s*$", re.I)


def check_player_seo(data, add, name, seo_title, sku, is_gift):
    if not sku or not sku["player"] or is_gift or re.fullmatch(r"(winners|champions)\s*\d*", fold(sku["player"])):
        return
    player = sku["player"].split()[0]
    if PLAYER_SUFFIX.search(name):
        add(MED, "SEO tên cầu thủ", "Tên sản phẩm",
            f"Tên cầu thủ đang ở cuối tên ('{PLAYER_SUFFIX.search(name).group(1).strip()}'): các URL cùng mẫu áo trùng phần đầu",
            "Đổi theo format: [Club] [PLAYER] [Số] [Home/Away] [Men/Kids] ... (giữ nguyên slug)")
    if seo_title:
        pos = fold(seo_title).find(fold(player))
        if pos == -1:
            add(HIGH, "SEO tên cầu thủ", "SEO title", f"SEO title không có tên cầu thủ '{player}': \"{seo_title}\"",
                "Thêm tên cầu thủ ngay sau tên CLB")
        elif pos > 45:
            add(MED, "SEO tên cầu thủ", "SEO title",
                f"Tên cầu thủ nằm ở ký tự {pos} của SEO title (Google cắt khoảng 60 ký tự): \"{seo_title}\"",
                "Đưa tên cầu thủ lên ngay sau tên CLB")
    h1 = data.get("page", {}).get("h1")
    if h1 is not None:
        miss = [w for w in (player, ) if fold(w) not in fold(h1)]
        if miss or not re.search(r"\b(shirt|kit)s?\b", h1, re.I):
            add(HIGH, "SEO tên cầu thủ", "H1", f"H1 thiếu tên cầu thủ hoặc thiếu Shirt/Kit: \"{h1}\"",
                "H1: [Club] [PLAYER] [Số] [Home/Away] [Men/Kids] [Shirt/Kit] [Season]")


def player_duplicate_groups(products, min_urls=5):
    """Kits with many near-identical player URLs (same base name once the player suffix is removed)."""
    groups = {}
    for d in products:
        n = strip_html(d["store"]["name"])
        base = PLAYER_SUFFIX.sub("", n).strip()
        groups.setdefault((d["site"], fold(base)), []).append(d)
    return {k: v for k, v in groups.items() if len(v) >= min_urls and any(PLAYER_SUFFIX.search(strip_html(x["store"]["name"])) for x in v)}


def check_extra_batch(products):
    """Duplicate product names on the same site (TC 029)."""
    seen = {}
    for d in products:
        seen.setdefault((d["site"], fold(strip_html(d["store"]["name"]))), []).append(d)
    out = []
    for (site, _), ds in player_duplicate_groups(products).items():
        ids = ", ".join(str(x["store"]["id"]) for x in ds)
        for d in ds:
            out.append((d, {"severity": LOW, "group": "SEO tên cầu thủ", "field": "Trùng lặp mẫu áo",
                            "detail": f"{len(ds)} URL cùng 1 mẫu áo chỉ khác cầu thủ ({ids}): nguy cơ ăn thịt từ khoá",
                            "fix": "Cầu thủ ít tìm kiếm: noindex hoặc canonical về listing gốc"}))
    for (_, _), ds in seen.items():
        if len(ds) > 1:
            ids = ", ".join(str(x["store"]["id"]) for x in ds)
            for d in ds:
                out.append((d, {"severity": MED, "group": "Trùng lặp", "field": "Tên sản phẩm",
                                "detail": f"Trùng tên với listing khác ({ids})", "fix": "Kiểm tra listing trùng, giữ 1 bản"}))
    return out


# ---------------------------------------------------------------- Part E: labelled fields of the new templates (22/10)
# KFK "Product Details", CFS "Kit Facts", short descriptions "What you get / Includes": every labelled value
# must agree with the listing. Anything a reader (or an AI) would find contradictory is an error.
def template_lines(raw):
    t = html.unescape(re.sub(r"<[^>]+>", "\n", raw or ""))
    return re.sub(r"[ \t]*\n\s*", "\n", t)


def field_value(text, *labels):
    for label in labels:
        m = re.search(rf"(?im)^\s*{label}\s*:\s*\n?\s*([^\n]+)", text)
        if m:
            return m.group(1).strip()
    return ""


def check_template_fields(data, add, name, sku, is_gift):
    s = data["store"]
    if is_gift:
        return
    desc, short = template_lines(s.get("description")), template_lines(s.get("short_description"))
    both = desc + "\n" + short
    long_name = bool(re.search(r"long[\s-]sleeve", name, re.I) or (sku and sku["long_sleeve"]))

    kit_v = field_value(desc, "Kit", "Kit type")
    if kit_v and kits_in(kit_v) and kits_in(name) and not kits_in(kit_v) & kits_in(name):
        add(HIGH, "Sai Home/Away/Third", "Description", f"Description ghi Kit: {kit_v}, nhưng tên là "
            f"{'/'.join(sorted(kits_in(name)))}", "Sửa ô Kit trong description")

    season_v = field_value(desc, "Season")
    if season_v:
        got = seasons_in(season_v) | set(YEAR_RE.findall(season_v))
        want = seasons_in(name) | set(YEAR_RE.findall(name))
        if got and want and not got & want:
            add(HIGH, "Sai season", "Description", f"Description ghi Season: {season_v}, tên sản phẩm là {', '.join(sorted(want))}",
                "Sửa ô Season trong description")

    sleeve_v = field_value(desc, "Sleeves", "Sleeve length")
    if sleeve_v and (("long" in sleeve_v.lower()) != long_name):
        add(HIGH, "Sleeve", "Description", f"Description ghi Sleeves: {sleeve_v}, nhưng tên là "
            f"{'Long Sleeve' if long_name else 'tay ngắn'}", "Sửa ô Sleeves trong description")

    socks = kit_socks(s, name)
    if socks == "with" and re.search(r"socks (are )?not included|without socks|no socks", both, re.I):
        add(HIGH, "Sai tất (socks)", "Description", "Listing With Socks nhưng description/short description ghi không có tất: "
            + snippet(both, r"socks (are )?not included|without socks|no socks", 40), "Sửa phần In the parcel / What you get")

    colours_v = field_value(desc, "Colours", "Main colours")
    name_cols = {c for c in KIT_COLOURS if re.search(rf"\b{c}\b", name, re.I)}
    if name_cols:
        where = colours_v or " ".join(desc.split()[:60])
        cols = {c for c in KIT_COLOURS if re.search(rf"\b{c}\b", where, re.I)}
        if cols and not name_cols & cols:
            add(MED, "Màu", "Description", f"Tên ghi màu {', '.join(sorted(name_cols))} nhưng description ghi "
                f"{', '.join(sorted(cols))}: \"{(colours_v or snippet(where, '|'.join(sorted(cols)), 40))[:90]}\"",
                "Sửa màu trong description cho đúng mẫu áo")

    sizes_v = field_value(both, "Sizes")
    aud = sku and sku["audience"]
    if sizes_v and aud in ("kids", "adult", "women"):
        says_kids = bool(re.search(r"\bkids?|ages?\b|yrs|\b(16|18|20|22|24|26|28)\b", sizes_v, re.I))
        says_adult = bool(re.search(r"\badult|\bmen|\b(S|M|L|XL|XXL)\b", sizes_v))
        if (aud == "kids" and says_adult and not says_kids) or (aud != "kids" and says_kids and not says_adult):
            add(HIGH, "Sai đối tượng", "Description", f"Listing {aud} nhưng description ghi Sizes: {sizes_v}",
                "Sửa ô Sizes trong description")

    nn = field_value(both, "Name and number", "Name & number")
    if sku and sku["player"] and nn and re.search(r"optional|available as an option|can be added|choose", nn, re.I):
        add(HIGH, "Sai cầu thủ", "Description", f"Listing in sẵn {sku['player']} nhưng ghi Name and number: {nn[:80]}",
            "Sửa thành: tên số in sẵn, không đổi được")
    if sku and not sku["player"] and re.search(r"pre-?printed with|player print:", both, re.I):
        add(HIGH, "Sai cầu thủ", "Description", "Listing không in sẵn nhưng description có Player print / Pre-printed: "
            + snippet(both, r"pre-?printed with|player print:", 40), "Xoá phần Player print (copy từ listing cầu thủ)")



def check_page_options(data, add, name):
    # Add-to-cart options (personalisation / badge labels) naming another kit: "Personalisation for Away shirt"
    # on a Home & Third bundle. The option forms are shared between products, so one wrong form hits many listings.
    name_kits = kits_in(name) - {"training"}
    for label in data.get("page", {}).get("options") or []:
        k = kits_in(label) - {"training"}
        if k and name_kits and not k <= name_kits:
            add(HIGH, "Sai Home/Away/Third", "Option sản phẩm",
                f"Option trên trang ghi \"{label[:80]}\" nhưng listing là {'/'.join(sorted(name_kits))}",
                "Sửa option (Extra Product Options / PPOM) gán cho sản phẩm này")


# ---------------------------------------------------------------- Part F: the whole product page (Clara 23/10)
# Everything on the page (options, variation names, short/long description, Size Guide / Delivery / Returns / Care
# tabs) must agree with the product name. "0% confusion": any line that names another kit, audience, team, season,
# socks option or print status is an error, wherever it sits.
KIT_CTX = re.compile(r"\b(home|away|third|fourth|goalkeeper|gk)\b[\s-]+(?!goalkeeper\b|gk\b)"
                     r"(?=(?:kits?|shirts?|jersey|strip|shorts|socks|football|replica|cheap|fan|men|mens|men's|kids?|"
                     r"women|adult|edition|version)\b)", re.I)
AUD_WORDS = {
    "kids": r"\b(?:men'?s|mens|men|adult|women'?s|women)\b",
    "adult": r"\b(?:kids?|kid'?s|junior|youth|children'?s|boys|girls)\b",
    "women": r"\b(?:men'?s|mens|men|kids?|kid'?s|junior)\b",
}
AUD_CTX = r"(?=[\s-]+(?:football\s+)?(?:shirts?|kits?|replica|cheap|sizes?|size\s+chart)\b)"
TYPOS = ["jusst", "recieve", "seperate", "guarentee", "definately", "delievery", "shrit", "persona1", "socsk", "sizez",
         "footbal ", "persnal", "qualty", "accross"]


def body_lines(body, pattern):
    return [ln.strip() for ln in body.split("\n") if re.search(pattern, ln, re.I)]


def product_text(body, own_name=""):
    """Body without what is not about this product: footer / menus that some themes put inside the product block,
    customer reviews, the delivery country table, "frequently bought together" product titles, raw HTML leaks."""
    end = re.search(r"\n(?:About Us|Search our store|All Categories)\n|Copyright\s*©", body)
    lines = (body[:end.start()] if end else body).split("\n")
    own = fold(own_name)
    keep = []
    for i, ln in enumerate(lines):
        st = ln.strip()
        if not st or "<" in st and ">" in st or "class=" in st:
            continue  # raw HTML of a bundle widget
        if re.match(r"[“\"★]", st):
            continue  # testimonial / rating widget: customers' words, not product info
        if any("working days" in x.lower() for x in lines[i + 1:i + 4]) or re.search(r"destinations|countries", st, re.I):
            continue  # delivery table: "Germany / 9–13 working days"
        if re.fullmatch(r"(?:choose\s+)?(?:home|away|third|goalkeeper)\s+kit\s+size", st, re.I):
            continue  # size pickers of a "buy together" bundle widget
        if (re.search(r"\b(gift (pack|bundle|set)|football (kit|shirt)s?)\b", st, re.I) and not st.endswith(".")
                and len(st.split()) <= 20 and fold(st) != own and not own.startswith(fold(st))):
            continue  # title of another product (cross-sell / bundle widget)
        keep.append(st)
    return "\n".join(keep)


def check_page_body(data, add, name, sku, is_gift, is_retro, team):
    s, body = data["store"], product_text(data["page"]["body"], name)
    # real sentences only: menus, tags, "Shop England World Cup 2026 Kits" links and short labels left out
    sentences = "\n".join(ln for ln in body.split("\n")
                          if len(ln.split()) >= 10 or len(ln.split()) >= 5 and re.search(r"[.!?:]$", ln))
    where = "Trang sản phẩm (option / tab / description)"

    # 1. Another kit type
    name_kits = kits_in(name) - {"training"}
    if name_kits:
        bad = []
        for m in KIT_CTX.finditer(body):
            k = kits_in(m.group(1))
            if k and not k <= name_kits:
                line = body[body.rfind("\n", 0, m.start()) + 1: (body.find("\n", m.end()) + 1 or len(body) + 1) - 1]
                bad.append(line.strip()[:90])
        if bad:
            add(HIGH, "Sai Home/Away/Third", where,
                f"Tên là {'/'.join(sorted(name_kits))} nhưng trang ghi: " + "; ".join(f'"{b}"' for b in list(dict.fromkeys(bad))[:3]),
                "Sửa mọi chỗ ghi sai loại áo (option personalisation, tên biến thể, description, tab)")

    # 2. Another audience (kids page showing a Men's size chart, men's page saying kids kit...)
    aud = sku and "/" not in (sku["aud_code"] or "") and sku["audience"]
    if aud in AUD_WORDS and not is_gift:
        bad = body_lines(body, AUD_WORDS[aud] + AUD_CTX)
        if bad:
            add(HIGH, "Sai đối tượng", where, f"Listing {aud} nhưng trang ghi: " + "; ".join(f'"{b[:90]}"' for b in bad[:3]),
                "Sửa chữ / bảng size cho đúng đối tượng")

    # 3. Another team
    ident = name + " " + team + " " + " ".join(TEAM_ALIASES.get(fold(team), []))
    national = bool(attr(s, "national team", "national teams")) or any(fold(team) == fold(c) for c in WORLD_CUP_2026_TEAMS)
    # a club page naturally names its country ("one of Germany's prominent teams"): countries only count on national pages
    pool = ENTITIES if national else [e for e in ENTITIES if e not in WORLD_CUP_2026_TEAMS]
    others = [e for e in pool if re.search(rf"\b{re.escape(e)}\b", sentences, re.I)
              and not re.search(rf"\b{re.escape(e)}\b", ident, re.I) and not fuzzy_contains(ident, e)
              and not fuzzy_contains(e, team or "~")]
    if others:
        lines = body_lines(sentences, rf"\b{re.escape(others[0])}\b")
        add(MED, "Sai team", where, f"Trang nhắc team khác: {', '.join(others[:3])}" + (f' ("{lines[0][:90]}")' if lines else ""),
            "Kiểm tra có copy nội dung từ listing team khác không")

    # 4. Another season (club listings with a season in the name)
    name_seasons = seasons_in(name)
    if name_seasons and not is_retro:
        other = seasons_in(sentences) - name_seasons
        if other:
            lines = body_lines(sentences, "|".join(o.replace("/", r"\s*/\s*(?:20)?") for o in other))
            add(HIGH, "Sai season", where, f"Tên là {', '.join(name_seasons)} nhưng trang có {', '.join(sorted(other))}"
                + (f': "{lines[0][:90]}"' if lines else ""), "Sửa season cho khớp")

    # 5. Socks
    socks = kit_socks(s, name) if has_word(fold(name), "kit") and not is_gift else None
    if socks == "with":
        bad = body_lines(body, r"socks (are )?not included|without socks|\bno socks\b")
    elif socks == "no":
        bad = body_lines(body, r"includes?\s+(matching\s+)?socks|socks (are )?included|shorts and (matching )?socks")
    else:
        bad = []
    if bad:
        add(HIGH, "Sai tất (socks)", where, f"Listing {'With' if socks == 'with' else 'No'} Socks nhưng trang ghi: \"{bad[0][:90]}\"",
            "Sửa cho khớp có/không có tất")

    # 6. Shirt-only listing talking about shorts
    if has_word(fold(name), "shirt") and not has_word(fold(name), "kit") and not is_gift:
        bad = [ln for ln in body_lines(body, r"matching shorts|shirt and shorts|shorts and socks|with shorts|"
                                                r"\bkid replica football kit\b")
               if not re.search(r"not included|shirt only", ln, re.I)]
        if bad:
            add(HIGH, "Sai loại Shirt/Kit", where, f"Listing chỉ là áo (Shirt) nhưng trang ghi: \"{bad[0][:90]}\"",
                "Bỏ phần nói về quần short / tất")

    # 7. Print status
    if sku and sku["player"]:
        bad = body_lines(body, r"personalis(e|ation) for|click .yes. for personali|select .yes. for personali|"
                               r"name and number:\s*(optional|available)")
        if bad:
            add(HIGH, "Sai cầu thủ", where, f"Listing in sẵn {sku['player']} nhưng trang vẫn cho/nhắc personalise: \"{bad[0][:90]}\"",
                "Bỏ option / đoạn personalisation trên listing in sẵn")
    elif sku:
        bad = body_lines(body, r"pre-?printed with|player print:")
        if bad:
            add(HIGH, "Sai cầu thủ", where, f"Listing không in sẵn nhưng trang ghi: \"{bad[0][:90]}\"",
                "Xoá phần Player print (copy từ listing cầu thủ)")

    # 8. Typos anywhere
    typos = [t.strip() for t in TYPOS if re.search(rf"\b{re.escape(t.strip())}\b", body, re.I)]
    if typos:
        lines = body_lines(body, re.escape(typos[0]))
        add(MED, "Lỗi chính tả", where, f"Sai chính tả: {', '.join(typos)}" + (f' ("{lines[0][:90]}")' if lines else ""),
            "Sửa chính tả")


# ---------------------------------------------------------------- Part G: KFK Christmas campaign + price on photos (23/10)
OCR_LOOKALIKE = {frozenset(p) for p in (("1", "4"), ("1", "7"), ("8", "9"), ("5", "9"), ("3", "8"), ("0", "8"), ("0", "6"))}


def ocr_same_price(read, real):
    """True when an OCR'd price is the real price with at most 2 look-alike digits misread
    (condensed fonts: "17.49" for 47.49, "77.48" for 71.49)."""
    a, b = f"{read:.2f}", f"{real:.2f}"
    if abs(read - real) < 0.06:
        return True
    if len(a) != len(b):
        return False
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    return len(diff) <= 2 and all(frozenset(d) in OCR_LOOKALIKE for d in diff)


def check_campaign_and_photo_price(data, add, name, site, is_gift):
    s, page = data["store"], data.get("page") or {}
    # Price printed on the main photo must be the selling price (KFK task 23/10: "live photos vs sale price")
    shown = page.get("image_price")
    price = site_price(s)
    if shown and price:
        regular = (s.get("prices") or {}).get("regular_price")
        ok = {round(price, 2)} | ({int(regular) / 100} if regular else set())
        if not any(ocr_same_price(x, y) for x in shown for y in ok):
            add(HIGH, "Kho / Giá", "Giá trên ảnh", f"Ảnh chính ghi £{max(shown):.2f} nhưng giá đang "
                f"bán là £{price:.2f}", "Làm lại ảnh với giá đúng (hoặc sửa giá nếu ảnh đúng)")

    # Christmas campaign: every listing published in the campaign window carries a Christmas AI image
    camp = CAMPAIGNS.get(site)
    published = (data.get("published_at") or "")[:10]
    if camp and published and camp["from"] <= published <= camp["until"]:
        imgs = s.get("images") or []
        if not any(XMAS_RE.search((i.get("src") or "") + " " + (i.get("alt") or "")) for i in imgs):
            add(HIGH, "Christmas campaign", "Ảnh", "Listing đăng trong đợt Christmas nhưng chưa có ảnh AI Christmas "
                "(không có ảnh nào tên/alt chứa Xmas/Christmas)", "Thêm ảnh AI Christmas (đặt tên file/alt có chữ Xmas)")


def check_photo_kit(data, add, name):
    """Main photo compared with the same team + season on all 4 sites: closer to another kit than to its own = wrong
    photo (CFS Switzerland 'Home' kit with the green Away photos, Clara 23/10)."""
    s, page = data["store"], data.get("page") or {}
    fp, key = page.get("image_colours"), photo_key(s, name)
    if not fp or not key:
        return
    me = f"{data['site']}:{s.get('id')}"
    same, other = [], {}
    for k, v in IMAGE_FP.items():
        if k == me or not v.get("key") or len(v.get("fp") or []) != len(fp) or v["key"][0] != key[0] or v["key"][1] != key[1] or v["key"][3] != key[3]:
            continue
        sim = colour_sim(fp, v["fp"])
        if v["key"][2] == key[2]:
            same.append(sim)
        else:
            other.setdefault(v["key"][2], []).append((sim, k))
    if not other:
        return
    kit, best = max(((k, max(v)) for k, v in other.items()), key=lambda x: x[1][0])
    best_same = max(same) if same else None
    if best_same is not None and best_same < 0.5 and best[0] >= 0.75:
        add(HIGH, "Sai Home/Away/Third", "Ảnh (màu áo)",
            f"Tên là {key[2]} nhưng màu áo trong ảnh chính giống áo {kit} của {key[0].title()} ({int(best[0] * 100)}%, "
            f"listing {best[1]}), chỉ giống áo {key[2]} {int(best_same * 100)}%", "Kiểm tra có upload nhầm ảnh áo khác không")
    elif best_same is None and best[0] >= 0.85:
        add(MED, "Sai Home/Away/Third", "Ảnh (màu áo)",
            f"Ảnh chính gần như trùng ảnh của listing {kit} {best[1]} ({int(best[0] * 100)}%): 1 trong 2 listing đang dùng "
            f"nhầm ảnh", "So với ảnh áo thật của mùa này, sửa listing bị nhầm")
