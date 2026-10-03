"""QA rules for one listing. Pure functions: product data in, list of issues out.

Rules come from the team's SEO / listing SOP (clara-ecom-ops skill):
audience, shirt vs kit, Home/Away/Third, team, season, player vs non-player,
socks, sleeve, Words to Avoid, site-required copy, SEO fields, images, stock.

Each issue: {severity, group, field, detail, fix}
  severity: "CAO" (sai thông tin / gây confuse khách & Google), "TB", "THAP"
"""

import html
import re
import unicodedata

HIGH, MED, LOW = "CAO", "TB", "THAP"

# ------------------------------------------------------------------ helpers


def strip_html(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(html.unescape(s))).strip()


def fold(s):
    """Lowercase, no accents: 'HØJLUND' -> 'hojlund'."""
    s = (s or "").replace("Ø", "O").replace("ø", "o").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def has_word(text, *words):
    return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text) for w in words)


def squash(s):
    """Letters only, undo brand-safe spellings: 'Lvr^_^pooI' / 'lvrp00l' -> 'lvrpooi' / 'lvrpool'."""
    s = fold(s).translate(str.maketrans({"0": "o", "@": "a", "1": "l", "$": "s", "3": "e"}))
    return re.sub(r"[^a-z]", "", s)


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fuzzy_contains(text, name):
    """True if `name`, or a brand-safe spelling of it (1-2 letters off), appears in `text`."""
    t, n = squash(text), squash(name)
    for drop in ("fc", "afc", "cf", "ssc", "club", "camisa"):
        if n.endswith(drop) and len(n) > len(drop) + 3:
            n = n[: -len(drop)]
        if n.startswith(drop) and len(n) > len(drop) + 3:
            n = n[len(drop):]
    if not n:
        return False
    if n in t:
        return True
    allowed = max(1, len(n) // 6)
    for size in (len(n) - 1, len(n), len(n) + 1):
        for i in range(max(1, len(t) - size + 1)):
            if edit_distance(n, t[i:i + size]) <= allowed:
                return True
    return False


def snippet(text, pattern, width=45):
    m = re.search(pattern, text, re.I)
    if not m:
        return ""
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("..." if a else "") + text[a:b] + ("..." if b < len(text) else "")


# ------------------------------------------------------------------ parsing

# ADK = Adult Kit (shirt + shorts), confirmed by Clara 27/9 (the old SOP said "adult + kid combo").
AUDIENCE_BY_SKU = {"AD": "adult", "WM": "women", "KD": "kids", "ADK": "adult", "BABY": "baby"}
AUDIENCE_LABEL = {"adult": "Men/Adult", "women": "Women", "kids": "Kids",
                  "adult+kids": "Adult + Kid", "baby": "Baby"}
KIT_WORDS = {"home": "home", "away": "away", "third": "third", "fourth": "fourth",
             "goalkeeper": "gk", "gk": "gk", "training": "training"}
SEASON_RE = re.compile(r"(?<![\d.])(20\d{2}|\d{2})\s*[/_-]\s*(\d{2})(?![\d.]|\s*(?:yrs|years|y\b|months|cm))")
YEAR_RE = re.compile(r"(?<![\d/])(20[12]\d)(?![\d/])")


def norm_season(m):
    a, b = m.group(1), m.group(2)
    a = a[-2:]
    if int(b) != (int(a) + 1) % 100 or not 18 <= int(a) <= 30:
        return None  # e.g. "16/28" sizes, not a season
    return f"{a}/{b}"


def seasons_in(text):
    return {s for s in (norm_season(m) for m in SEASON_RE.finditer(text or "")) if s}


def parse_sku(sku):
    parts = (sku or "").split("_")
    if len(parts) != 6:
        return None
    site, team, kit, aud, player, season = parts
    kit_u = kit.upper()
    kits = set()
    for code, k in (("HO", "home"), ("AW", "away"), ("TH", "third"), ("GK", "gk"), ("TN", "training")):
        if code in kit_u:
            kits.add(k)
    return {
        "site": site, "team": team, "kit_code": kit, "kits": kits,
        "gift": "GP" in kit_u, "long_sleeve": bool(re.search(r"L[SV]$", kit_u)),
        "audience": AUDIENCE_BY_SKU.get(aud.upper()), "aud_code": aud,
        "player": None if player.lower() == "no" else html.unescape(player),
        "season_raw": season, "season": next(iter(seasons_in(season)), None),
    }


def audience_in(text):
    """Audiences mentioned in a (folded) text."""
    t = fold(text)
    found = set()
    if has_word(t, "kid", "kids", "kid's", "kids'", "children", "childrens", "junior", "boys", "youth"):
        found.add("kids")
    if has_word(t, "men", "mens", "men's", "adult", "adults", "dad"):
        found.add("adult")
    if has_word(t, "women", "womens", "women's", "ladies", "womans"):
        found.add("women")
    if has_word(t, "baby", "infant"):
        found.add("baby")
    return found


def product_type_in(text):
    t = fold(text)
    found = set()
    if has_word(t, "kit", "kits"):
        found.add("kit")
    if has_word(t, "shirt", "shirts", "jersey"):
        found.add("shirt")
    return found


def kits_in(text):
    t = fold(text)
    return {v for k, v in KIT_WORDS.items() if has_word(t, k)}


def attr(store, *names):
    for a in store.get("attributes", []):
        if fold(a["name"]) in names:
            return [html.unescape(t["name"]) for t in a.get("terms", [])]
    return []


def size_kind(terms):
    kinds = set()
    for t in terms:
        tl = fold(t)
        if "yrs" in tl or "month" in tl or re.match(r"^\d{2}\b", tl):
            kinds.add("kids")
        elif re.match(r"^(x{0,3}s|m|x{0,4}l|\d?xl)\b", tl):
            kinds.add("adult")
    return kinds


# ------------------------------------------------------------------ rules

WORDS_TO_AVOID = [
    (r"official", "football-inspired"),
    (r"authentic", "football-inspired"),
    (r"exact design", "inspired design"),
    (r"faithfully recreates?", "takes inspiration from"),
    (r"identical to the originals?", "closely inspired"),
    (r"the originals", "familiar football styles"),
    (r"original shirts?", "football shirts"),
    (r"precise duplicates?", "football-inspired designs"),
    (r"real (?:shirts|kits)", "football shirts and kits"),
    (r"nike|adidas|puma|errea|erreà|macron|snapdragon|swoosh|three stripes", "brand detail"),
    (r"(?:club |team )?crest", "chest detail"),
    (r"(?<!sleeve )badge", "chest detail"),
    (r"emblem", "chest detail"),
    (r"(?:sleeve |main |shirt )?sponsor(?: logo)?", "front graphic / sleeve detail"),
    (r"on the chest|across the chest", "on the front"),
    (r"proudly displays", "features"),
    (r"(?:displays|features|showcases) the", "includes the / highlights the"),
    (r"complete with", "comes with"),
    (r"anfield|old trafford|san siro|camp nou|bernabeu|emirates stadium|etihad", "(bỏ tên sân)"),
    (r"logo", "printed detail"),
    (r"trustpilot", "(bỏ claim không kiểm chứng)"),
    (r"verified", "(bỏ)"),
    (r"worldwide", "(bỏ)"),
]
WORDS_TO_AVOID_RE = [(re.compile(rf"(?<![a-z]){p}(?![a-z])", re.I), fix) for p, fix in WORDS_TO_AVOID]

RFS_REQUIRED = ("our package contains exactly what is shown in the product pictures "
                "at the time you placed your order")

# Brand-safe names used on the sites instead of the real club name.
TEAM_ALIASES = {
    "arsenal": ["north london red"],
    "tottenham hotspur": ["north london white", "spurs"],
    "paris saint-germain": ["p^_^sg", "psg"],
}

SHARED_IMAGE_RE = re.compile(r"size chart|size guide|delivery|infographic|inforgraphic|shipping", re.I)


def check_product(data, extra=True):
    """Return list of issues for one cached product ({site, store, page})."""
    site, s, page = data["site"], data["store"], data.get("page", {})
    issues = []

    def add(sev, group, field, detail, fix=""):
        issues.append({"severity": sev, "group": group, "field": field, "detail": detail, "fix": fix})

    name = strip_html(s.get("name"))
    desc = strip_html(s.get("description"))
    short = strip_html(s.get("short_description"))
    seo_title = page.get("seo_title", "")
    meta = page.get("meta_description", "")
    alts = [(strip_html(i.get("alt")), i.get("src", "")) for i in s.get("images", [])]
    product_alts = [(a, src) for a, src in alts if not SHARED_IMAGE_RE.search(a + " " + src)]
    sku = parse_sku(s.get("sku"))
    fname = fold(name)
    is_gift = sku and sku["gift"] or has_word(fname, "gift", "bundle", "pack")
    is_retro = has_word(fname, "retro")
    blocked = bool(page.get("blocked"))  # page HTML not readable: SEO fields unknown, not empty
    seo_fields = [] if blocked else [("SEO title", seo_title), ("Meta description", meta)]

    # ---------- SKU
    if not s.get("sku"):
        add(HIGH, "SKU", "SKU", "Thiếu SKU", "Thêm SKU theo format SITE_TEAM_KIT_AUD_PLAYER_SEASON")
    elif sku is None:
        add(MED, "SKU", "SKU", f"SKU sai format: {s['sku']}", "Format: SITE_TEAM_KIT_AUD_PLAYER_SEASON")
    else:
        if sku["site"] != site:
            add(HIGH, "SKU", "SKU", f"SKU bắt đầu bằng {sku['site']} nhưng listing ở {site}",
                f"Đổi prefix SKU thành {site}_")
        if re.search(r"&#\d+;|&amp;", s["sku"]):
            add(MED, "SKU", "SKU", f"SKU chứa ký tự mã hoá HTML: {s['sku']}", "Thay '&#038;' bằng '&' hoặc '+'")
        if sku["audience"] is None:
            add(MED, "SKU", "SKU", f"Mã đối tượng trong SKU không rõ: {sku['aud_code']}", "Dùng AD / KD / WM / ADK / BABY")
        if sku["season"] and sku["season_raw"] != sku["season"] and not is_retro:
            add(LOW, "SKU", "SKU", f"Season trong SKU ghi '{sku['season_raw']}', các SKU khác ghi '{sku['season']}'",
                f"Đổi thành {sku['season']}")

    # ---------- Audience
    if sku and sku["audience"]:
        exp = sku["audience"]
        exp_set = {"adult", "kids"} if exp == "adult+kids" else {exp}
        name_aud = audience_in(name)
        if name_aud and not is_gift:
            if exp == "adult+kids" and name_aud != exp_set:
                add(HIGH, "Sai đối tượng", "Tên sản phẩm",
                    f"SKU '{sku['aud_code']}' (Adult + Kid) nhưng tên chỉ ghi {', '.join(AUDIENCE_LABEL[a] for a in sorted(name_aud))}",
                    "Kiểm tra lại: sửa tên hoặc đổi SKU cho đúng")
            elif exp != "adult+kids" and not name_aud & exp_set:
                add(HIGH, "Sai đối tượng", "Tên sản phẩm",
                    f"SKU '{sku['aud_code']}' ({AUDIENCE_LABEL[exp]}) nhưng tên ghi {', '.join(AUDIENCE_LABEL[a] for a in sorted(name_aud))}",
                    "Sửa tên hoặc SKU cho khớp")
        age = attr(s, "gender/age", "age", "gender")
        age_aud = audience_in(" ".join(age))
        if age_aud and not age_aud & exp_set and not is_gift:
            add(HIGH, "Sai đối tượng", "Attribute Gender/Age",
                f"Attribute ghi '{', '.join(age)}' nhưng SKU là {AUDIENCE_LABEL[exp]}", "Sửa attribute Gender/Age")
        sizes = attr(s, "size", "sizes")
        kinds = size_kind(sizes)
        if kinds and not is_gift:
            if exp == "kids" and "adult" in kinds:
                add(HIGH, "Sai đối tượng", "Size", "Listing Kids nhưng có size người lớn (S/M/L/XL)",
                    "Bỏ size adult, dùng size kids")
            if exp in ("adult", "women") and kinds == {"kids"}:
                add(HIGH, "Sai đối tượng", "Size", f"Listing {AUDIENCE_LABEL[exp]} nhưng chỉ có size trẻ em",
                    "Đổi sang size adult")
        if not is_gift:
            for field, text in seo_fields:
                aud = audience_in(text)
                wrong = aud - exp_set - ({"adult"} if exp == "women" else set())
                if exp in ("adult", "women") and re.search(r"birthday gift for kids|uk parents|kids gift", fold(text)):
                    wrong.add("kids")
                if wrong:
                    add(HIGH, "Sai đối tượng", field,
                        f"Listing {AUDIENCE_LABEL[exp]} nhưng {field} nhắc tới {', '.join(AUDIENCE_LABEL[a] for a in sorted(wrong))}: \"{text}\"",
                        f"Viết lại {field} theo đúng đối tượng {AUDIENCE_LABEL[exp]}")

    # ---------- Shirt vs Kit
    name_type = product_type_in(name)
    if len(name_type) == 1 and not is_gift:
        nt = next(iter(name_type))
        other = "shirt" if nt == "kit" else "kit"
        for field, text in seo_fields:
            t = product_type_in(text)
            if other in t and nt not in t:
                add(HIGH, "Sai loại Shirt/Kit", field,
                    f"Tên là {nt.upper()} nhưng {field} ghi {other.upper()}: \"{text}\"",
                    f"Đổi '{other}' thành '{nt}' trong {field}")
        if nt == "shirt" and re.search(r"(includes?|comes with|with) (a )?(matching )?shorts", desc, re.I):
            add(HIGH, "Sai loại Shirt/Kit", "Description",
                "Tên là SHIRT nhưng description nói có kèm quần short: " + snippet(desc, r"shorts"),
                "Sửa description: chỉ có áo")

    # ---------- Home / Away / Third / GK
    name_kits = kits_in(name)
    if name_kits:
        if sku and sku["kits"] and sku["kits"] != name_kits and not (sku["gift"] and sku["kits"] <= name_kits):
            gk_third = "gk" in name_kits and sku["kits"] == {"third"}  # maybe a third goalkeeper kit
            add(MED if gk_third else HIGH, "Sai Home/Away/Third", "SKU",
                f"Tên ghi {'/'.join(sorted(name_kits))} nhưng SKU ghi {sku['kit_code']}", "Sửa SKU hoặc tên")
        kit_attr = kits_in(" ".join(attr(s, "kit type", "type")))
        if kit_attr and not kit_attr <= name_kits and not is_gift:
            add(HIGH, "Sai Home/Away/Third", "Attribute Kit Type",
                f"Attribute ghi {', '.join(attr(s, 'kit type', 'type'))} nhưng tên là {'/'.join(sorted(name_kits))}",
                "Sửa attribute Kit Type")
        for field, text in seo_fields:
            k = kits_in(text)
            if k and not k & name_kits:
                add(HIGH, "Sai Home/Away/Third", field,
                    f"Tên là {'/'.join(sorted(name_kits))} nhưng {field} ghi {'/'.join(sorted(k))}: \"{text}\"",
                    f"Sửa {field}")
        # Opening of the description names the product: copy from another kit shows up here.
        intro = " ".join(desc.split()[:80])
        k = kits_in(intro) - {"training"} - name_kits
        if k and not is_gift:
            add(HIGH, "Sai Home/Away/Third", "Description",
                f"Tên là {'/'.join(sorted(name_kits))} nhưng đầu description ghi {'/'.join(sorted(k))}: "
                + snippet(intro, "|".join("goalkeeper|gk" if x == "gk" else x for x in k), 60),
                "Sửa description (có thể copy từ listing khác)")
        bad_alts = [a for a, _ in product_alts if kits_in(a) and not kits_in(a) & name_kits]
        if bad_alts and not is_gift:
            add(MED, "Sai Home/Away/Third", "Ảnh / alt text",
                f"{len(bad_alts)} ảnh có alt ghi khác loại áo (vd: \"{bad_alts[0]}\")",
                "Kiểm tra ảnh có đúng mẫu áo không, sửa alt text")

    # ---------- Team
    team = attr(s, "clubs name", "club", "clubs", "national team", "national teams", "team")
    if team:
        t0 = fold(team[0])
        names = [t0] + TEAM_ALIASES.get(t0, [])

        def mentions_team(text):
            return any(fuzzy_contains(text, n) for n in names)

        if not mentions_team(name) and not is_gift:
            add(HIGH, "Sai team", "Attribute Clubs Name",
                f"Attribute team là '{team[0]}' nhưng tên sản phẩm không có", "Sửa attribute hoặc tên")
        for field, text in seo_fields:
            if text and not mentions_team(text):
                add(MED, "Sai team", field, f"{field} không nhắc tên team '{team[0]}': \"{text}\"",
                    f"Thêm tên team vào {field}")
        cats = [fold(c["name"]) for c in s.get("categories", [])]
        if not any(fuzzy_contains(c, n) or fuzzy_contains(n, c) for c in cats for n in names):
            add(MED, "Category / Tag", "Category", f"Không có category của team '{team[0]}'",
                "Thêm category team")

    # ---------- Season
    name_seasons = seasons_in(name)
    if not is_retro:
        if name_seasons:
            ns = next(iter(name_seasons))
            if ns != "26/27":
                add(MED, "Sai season", "Tên sản phẩm", f"Listing mới nhưng season là {ns}, không phải 26/27",
                    "Kiểm tra lại season (club: 26/27, đội tuyển: 2026, retro: giữ nguyên)")
            for field, text in [("SKU", s.get("sku", "")), ("Attribute Season", " ".join(attr(s, "season")))] + seo_fields:
                other = seasons_in(text) - name_seasons
                if other:
                    add(HIGH, "Sai season", field, f"Tên ghi {ns} nhưng {field} ghi {', '.join(sorted(other))}",
                        f"Sửa season trong {field}")
            # Only last seasons: history copy ("won the league in 2019/20") is fine.
            other = (seasons_in(desc) - name_seasons) & {"24/25", "25/26"}
            if other:
                add(HIGH, "Sai season", "Description",
                    f"Tên ghi {ns} nhưng description có {', '.join(sorted(other))}: "
                    + snippet(desc, "|".join(re.escape(o.split('/')[0]) + r"\s*[/_-]\s*" + o.split('/')[1] for o in other)),
                    "Sửa season trong description")
            bad = [a for a, _ in product_alts if seasons_in(a) - name_seasons]
            if bad:
                add(MED, "Sai season", "Ảnh / alt text", f"{len(bad)} ảnh có alt ghi season khác (vd: \"{bad[0]}\")",
                    "Sửa alt text / kiểm tra ảnh")
        else:
            years = set(YEAR_RE.findall(name))
            if years and years != {"2026"} and has_word(fname, "world cup", "national"):
                add(MED, "Sai season", "Tên sản phẩm", f"Đội tuyển quốc gia nhưng năm là {', '.join(years)}",
                    "Đội tuyển dùng 2026")

    # ---------- Player vs non-player
    players_attr = attr(s, "players", "player")
    cats_f = [fold(html.unescape(c["name"])) for c in s.get("categories", [])]
    if sku and sku["player"]:
        p = sku["player"]
        p_words = [w for w in re.split(r"[^a-z0-9]+", fold(p)) if w and not w.isdigit()]
        if p_words and not all(w in fname for w in p_words):
            add(HIGH, "Sai cầu thủ", "Tên sản phẩm", f"SKU có cầu thủ '{p}' nhưng tên không có", "Sửa tên hoặc SKU")
        up = re.search(r"[A-ZÀ-ÝØ.\-']{2,}(?:\s[A-ZÀ-ÝØ.\-']{2,})*\s\d{1,2}", name)
        if not up and not is_gift:
            add(LOW, "Sai cầu thủ", "Tên sản phẩm", "Tên + số cầu thủ chưa VIẾT HOA", "Viết hoa tên + số cầu thủ")
        # "CHAMPIONS 26" style prints need no player attribute/category (Clara 27/9)
        commemorative = re.fullmatch(r"(winners|champions)\s*\d*", fold(p))
        if not players_attr and not commemorative:
            add(HIGH, "Sai cầu thủ", "Attribute Players",
                f"Listing cầu thủ '{p}' nhưng THIẾU player attribute (không hiện trong filter cầu thủ)",
                "Thêm attribute Players")
        if p_words and not is_gift and not commemorative and not any(all(w in c for w in p_words) for c in cats_f):
            add(MED, "Sai cầu thủ", "Category", f"Thiếu player category cho '{p}'", "Thêm player category")
        if re.search(r"personalisation options|how to add personalisation|add your own name", desc, re.I):
            add(HIGH, "Sai cầu thủ", "Description",
                "Listing cầu thủ (in sẵn) nhưng description vẫn có phần Personalisation Options",
                "Xoá phần Personalisation Options / How to add personalisation")
    elif sku:
        if players_attr:
            add(HIGH, "Sai cầu thủ", "Attribute Players",
                f"SKU là 'No' (không in) nhưng có player attribute: {', '.join(players_attr)}",
                "Xoá player attribute hoặc sửa SKU")
        for field, text in [("Tên sản phẩm", name)] + seo_fields:
            if re.search(r"\b[A-Z][A-Z.\-']{2,} \d{1,2}\b", text) and not is_gift:
                add(HIGH, "Sai cầu thủ", field, f"SKU là 'No' nhưng {field} có tên + số cầu thủ: \"{text}\"",
                    "Kiểm tra SKU / tên")
            elif field != "Tên sản phẩm" and re.search(r"personali[sz]|custom name|custom number|printed", text, re.I):
                add(MED, "Sai cầu thủ", field, f"Listing không in sẵn nhưng {field} nhắc personalise/printed: \"{text}\"",
                    f"Bỏ personalise/custom/printed khỏi {field}")

    # ---------- Socks
    fsocks = fold(name)
    kit_opt = fold(" ".join(attr(s, "kit option", "socks")))
    name_socks = "with" if "with socks" in fsocks else "no" if re.search(r"no socks|without socks", fsocks) else None
    if name_socks:
        attr_socks = "with" if "with socks" in kit_opt else "no" if re.search(r"no socks|without", kit_opt) else None
        if attr_socks and attr_socks != name_socks:
            add(HIGH, "Sai tất (socks)", "Attribute Kit Option",
                f"Tên ghi {name_socks} socks nhưng attribute ghi '{kit_opt}'", "Sửa attribute Kit Option")
        fdesc = fold(desc)
        if name_socks == "no" and re.search(r"matching socks|shorts and socks|shorts, and socks|kit includes[^.]*socks", fdesc):
            add(HIGH, "Sai tất (socks)", "Description", "Tên ghi No Socks nhưng description nói có kèm tất: "
                + snippet(desc, r"socks"), "Sửa description")
        if name_socks == "with" and re.search(r"socks (are )?not included|no socks|without socks", fdesc):
            add(HIGH, "Sai tất (socks)", "Description", "Tên ghi With Socks nhưng description nói không có tất: "
                + snippet(desc, r"socks"), "Sửa description")

    # ---------- Sleeve
    # Mentioning the sleeve is fine as long as it matches the product (Clara 27/9).
    img_text = fold(" ".join(a + " " + src for a, src in product_alts))
    is_long = (has_word(fname, "long sleeve") or bool(sku and sku["long_sleeve"])
               or bool(re.search(r"long[\s_-]?sleeve", img_text)))
    for field, text in [("Description", desc), ("Short description", short)] + seo_fields:
        if is_long and re.search(r"short[\s-]sleeves?", text, re.I):
            add(HIGH, "Sleeve", field, "Sản phẩm là Long Sleeve nhưng ghi 'short sleeve': "
                + snippet(text, r"short[\s-]sleeve"), "Sửa thành long sleeve cho khớp ảnh/tên")
        if not is_long and re.search(r"(includes?|with|supplied with|features?) (a |the )?long[\s-]sleeved?\b(?! option)",
                                     text, re.I):
            add(HIGH, "Sleeve", field, "Sản phẩm không phải Long Sleeve nhưng ghi áo dài tay: "
                + snippet(text, r"long[\s-]sleeve"), "Sửa cho khớp ảnh/tên")
    if sku and has_word(fname, "long sleeve") != sku["long_sleeve"]:
        add(HIGH, "Sleeve", "SKU", f"Tên {'có' if 'long sleeve' in fname else 'không có'} Long Sleeve nhưng SKU là {sku['kit_code']}",
            "Sửa SKU / tên")

    # ---------- Words to Avoid
    for field, text in [("Tên sản phẩm", name), ("Description", desc), ("Short description", short)] + seo_fields:
        hits = []
        for rx, fix in WORDS_TO_AVOID_RE:
            m = rx.search(text)
            if m:
                hits.append((m.group(0), fix, snippet(text, re.escape(m.group(0)), 30)))
        if hits:
            add(HIGH if field in ("Tên sản phẩm", "SEO title", "Meta description") else MED,
                "Words to Avoid", field,
                "; ".join(f"'{h[0]}' ({h[2]})" for h in hits),
                "; ".join(f"{h[0]} -> {h[1]}" for h in hits))

    # ---------- Site-required copy
    if site == "RFS":
        if RFS_REQUIRED not in fold(desc):
            add(MED, "Thiếu nội dung bắt buộc", "Description",
                "Thiếu câu bắt buộc của RFS: 'Our package contains exactly what is shown in the product pictures at the time you placed your order.'",
                "Thêm câu bắt buộc vào description")
        n_li = len(re.findall(r"<li", s.get("short_description") or "", re.I))
        if n_li and n_li != 3:
            add(LOW, "Thiếu nội dung bắt buộc", "Short description", f"RFS short description có {n_li} bullet (quy tắc: đúng 3)",
                "Sửa lại còn 3 bullet")

    # ---------- SEO fields
    if blocked:
        add(LOW, "SEO", "Trang sản phẩm", "Không đọc được trang (tường lửa chặn tool): chưa check SEO title, meta, canonical",
            "Whitelist IP tool trên Cloudflare")
    elif not seo_title:
        add(HIGH, "SEO", "SEO title", "Không đọc được SEO title trên trang", "Kiểm tra Rank Math")
    elif len(seo_title) > 65:
        add(LOW, "SEO", "SEO title", f"SEO title dài {len(seo_title)} ký tự (nên <= 60)", "Rút gọn")
    if not meta and not blocked:
        add(HIGH, "SEO", "Meta description", "Thiếu meta description", "Viết meta description")
    elif len(meta) > 165:
        add(LOW, "SEO", "Meta description", f"Meta dài {len(meta)} ký tự (nên <= 160)", "Rút gọn")
    for field, text in seo_fields:
        probs = []
        if re.search(r"\s[,.!?;:]", text):
            probs.append("khoảng trắng trước dấu câu")
        if "  " in text:
            probs.append("2 dấu cách liền nhau")
        if re.search(r"%\w+%|\{\{", text):
            probs.append("biến chưa được thay (%...%)")
        if re.search(r"&(amp|#\d+);", text):
            probs.append("ký tự HTML (&amp;...)")
        if "&" in text or '"' in text:
            probs.append("có ký tự & hoặc \"")
        if probs:
            add(LOW, "SEO", field, f"{', '.join(probs)}: \"{text}\"", "Sửa định dạng")
    robots = page.get("robots", "")
    if "noindex" in robots and not is_gift:  # gift packs are noindex on purpose (Clara 27/9)
        add(HIGH, "SEO", "Robots", f"Trang đang NOINDEX ({robots}) -> Google không index", "Bật index trong Rank Math")
    canon = page.get("canonical", "")
    if canon and canon.rstrip("/") != s.get("permalink", "").rstrip("/"):
        add(HIGH, "SEO", "Canonical",
            f"Canonical trỏ sang URL khác -> Google sẽ không index listing này: {canon}",
            "Xoá/sửa canonical URL trong Rank Math (Advanced) cho đúng URL của listing")

    # ---------- Images
    if not alts:
        add(HIGH, "Ảnh", "Ảnh", "Listing không có ảnh", "Thêm ảnh")
    else:
        empty = sum(1 for a, _ in alts if not a)
        if empty:
            add(MED, "Ảnh", "Alt text", f"{empty}/{len(alts)} ảnh không có alt text", "Thêm alt text riêng cho từng ảnh")
        seen, dup = set(), set()
        for a, _ in product_alts:
            if a and a in seen:
                dup.add(a)
            seen.add(a)
        if dup:
            add(LOW, "Ảnh", "Alt text", f"Alt text bị trùng giữa các ảnh: \"{next(iter(dup))}\"", "Mỗi ảnh 1 alt riêng")
        if sku and sku["audience"] in ("adult", "women", "kids") and not is_gift:
            for a, src in alts:
                t = fold(a + " " + src)
                if "size" in t and "chart" in t:
                    chart_aud = audience_in(re.sub(r"[-_./]", " ", t))
                    exp = sku["audience"]
                    if chart_aud and exp not in chart_aud and not (exp == "women" and "adult" in chart_aud):
                        add(HIGH, "Ảnh", "Size chart",
                            f"Listing {AUDIENCE_LABEL[exp]} nhưng dùng size chart {', '.join(AUDIENCE_LABEL[x] for x in chart_aud)} ({src.rsplit('/', 1)[-1]})",
                            "Đổi size chart đúng đối tượng")

    # ---------- Stock / price / variations
    if not s.get("is_in_stock", True):
        add(MED, "Kho / Giá", "Stock", "Listing mới nhưng đang HẾT HÀNG (bị ẩn khỏi shop)", "Kiểm tra stock các variation")
    price = (s.get("prices") or {}).get("price")
    if price in ("0", "", None) and s.get("type") != "variable":
        add(HIGH, "Kho / Giá", "Giá", "Giá = 0 hoặc trống", "Nhập giá")
    if s.get("type") == "variable" and not s.get("variations") and s.get("is_in_stock", True):
        add(HIGH, "Kho / Giá", "Variation", "Sản phẩm variable nhưng không có variation nào", "Tạo variation")

    # ---------- Tags
    for t in s.get("tags", []):
        if fold(html.unescape(t["name"])) == fname:
            add(LOW, "Category / Tag", "Tag", f"Tag trùng tên sản phẩm: {t['name']}", "Xoá tag này")

    if extra:
        from qa_rules_extra import check_extra  # rules added 2/10 (KFK QA checker + new cases)
        issues.extend(check_extra(data))
    return issues


def check_batch(products, extra=True):
    """Cross-product checks: duplicate SEO title / meta within a site."""
    issues = []
    for field in ("seo_title", "meta_description"):
        seen = {}
        for d in products:
            v = d.get("page", {}).get(field, "")
            if v:
                seen.setdefault((d["site"], v), []).append(d)
        for (site, v), ds in seen.items():
            if len(ds) > 1:
                ids = ", ".join(str(x["store"]["id"]) for x in ds)
                for d in ds:
                    issues.append((d, {
                        "severity": HIGH if field == "seo_title" else MED, "group": "SEO",
                        "field": "SEO title" if field == "seo_title" else "Meta description",
                        "detail": f"Trùng với {len(ds) - 1} listing khác ({ids}): \"{v}\"",
                        "fix": "Viết riêng cho từng listing"}))
    if extra:
        from qa_rules_extra import check_extra_batch
        issues.extend(check_extra_batch(products))
    return issues
