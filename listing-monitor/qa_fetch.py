"""Download everything the QA rules need for one product (public data only).

  - Store API product: name, SKU, description, attributes, tags, images, stock...
  - Product page <head>: SEO title, meta description, robots, canonical
    (what Rank Math actually outputs, i.e. what Google sees).

Results are cached in data/cache/<SITE>/<id>.json so re-runs are fast.
"""

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from check_new_listings import BASE_DIR, USER_AGENT, http_get

CACHE_DIR = BASE_DIR / "data" / "cache"


def fetch_head(url, timeout=30, retry_waits=(20, 60)):
    """Only the <head> of a page: product pages are ~500KB, the head is enough."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for wait in (*retry_waits, None):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                buf = b""
                while b"</head>" not in buf:
                    chunk = resp.read(32768)
                    if not chunk:
                        break
                    buf += chunk
                return buf.decode("utf-8-sig", errors="replace")
        except urllib.error.HTTPError as e:
            if wait is None or not (e.code in (403, 429) or e.code >= 500):
                raise
            if e.code == 403 and b"Attention Required" in (e.read(4096) or b""):
                raise  # Cloudflare firewall block (not a burst limit): retrying will not help
            time.sleep(wait)


def _meta(head, pattern):
    m = re.search(pattern, head, re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def parse_head(head):
    return {
        "seo_title": _meta(head, r"<title[^>]*>(.*?)</title>"),
        "meta_description": _meta(head, r'<meta name="description" content="([^"]*)"'),
        "robots": _meta(head, r'<meta name="robots" content="([^"]*)"'),
        "canonical": _meta(head, r'<link rel="canonical" href="([^"]*)"'),
    }


def parse_h1(page_html):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html or "", re.S | re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else None


def parse_options(page_html):
    """Labels of the add-to-cart options (personalisation, badges): Extra Product Options (RFS/RFK) and PPOM (KFK/CFS)."""
    t = page_html or ""
    labels = re.findall(r'class="[^"]*tm-epo-element-label[^"]*"[^>]*>([^<]+)<', t)
    labels += re.findall(r'data-title="([^"]+)"', t) + re.findall(r'data-label="([^"]+)"', t)
    out = []
    for raw in labels:
        label = html.unescape(raw).strip()
        if label and label not in out and label.lower() not in ("checkbox", "yes", "no"):
            out.append(label)
    return out


def parse_badges(page_html):
    """Sleeve badge options with their pictures, for sleeve_badge.py: [{'label', 'images'}].
    CFS (PPOM): the checkbox's data-label ("Add Premier Badge"). KFK/RFS/RFK (Extra Product Options): the
    option label plus the alt text and filename of each picture under it, because labels like "Add  Badge"
    or "Add Combo Argentina Home 2026 Badge" only name the league in the picture."""
    t = page_html or ""
    badges = []
    for tag in re.findall(r'<input[^>]*data-data_name="?badge"?[^>]*>', t):
        m = re.search(r'data-label="([^"]*)"', tag)
        if m and "badge" in m.group(1).lower():
            badges.append({"label": html.unescape(m.group(1)).strip(), "images": []})
    for m in re.finditer(r'<(label|h\d|span|div)\b[^>]*class="[^"]*tm-epo-element-label[^"]*"[^>]*>(.*?)</\1>', t, re.S):
        label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        if "badge" not in label.lower():
            continue
        # the picture block under the label, up to the option's own input / the next option
        rest = t[m.end():m.end() + 8000]
        stop = re.search(r'tc-element-container|tm-epo-element-label|tc-element-inner-wrap', rest)
        images = []
        for img in re.findall(r"<img[^>]*>", rest[:stop.start() if stop else len(rest)]):
            alt = re.search(r'\balt="([^"]*)"', img)
            srcs = [re.search(rf'(?<![\w-]){a}="([^"]+)"', img) for a in ("data-src", "data-lazy-src", "src")]
            src = next((s.group(1) for s in srcs if s and not s.group(1).startswith("data:")), "")
            for x in (html.unescape(alt.group(1)).strip() if alt else "", src.rsplit("/", 1)[-1]):
                if x:
                    images.append(x)
        badges.append({"label": label, "images": images})
    return badges


def parse_body(page_html):
    """Visible text of the product block only (summary, options, variations, all tabs), without menus,
    related products, footer, scripts. This is everything a shopper (or an AI) reads about the product."""
    t = page_html or ""
    m = re.search(r'<div[^>]*id="product-\d+', t)
    if not m:
        return ""
    st = m.start()
    end = re.search(r"<section[^>]*related|related products|<footer|you may also like", t[st:], re.I)
    region = t[st:st + (end.start() if end else 150000)]
    region = re.sub(r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", region, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", region))
    return re.sub(r"[ \t\u00a0]*\n\s*", "\n", text).strip()


def colour_print(im):
    """Colour make-up of the kit in a product photo: 12 hues x (light, dark) + white + black + grey, normalised.
    White studio background and the bottom badge strip are left out. Light/dark keeps sky blue apart from navy."""
    w, h = im.size
    small = im.crop((int(w * 0.08), int(h * 0.08), int(w * 0.92), int(h * 0.80))).resize((80, 80)).convert("HSV")
    bins = [0.0] * 27
    for hh, ss, vv in small.getdata():
        if vv > 235 and ss < 20:
            continue  # background
        if vv < 50:
            bins[25] += 1
        elif ss < 40:
            bins[24 if vv > 200 else 26] += 1
        else:
            bins[hh * 12 // 256 * 2 + (0 if vv > 150 else 1)] += 1
    total = sum(bins) or 1
    return [round(b / total, 3) for b in bins]


def load_image(src, timeout=30):
    from PIL import Image
    import io
    req = urllib.request.Request(safe_url(src), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGB")


def image_price(src, timeout=30, im=None):
    """Prices printed on a product photo (gift pack "SPECIAL OFFER £49.99" badge), read with OCR.
    None when OCR is not installed or the image cannot be read; [] when no price is printed."""
    try:
        import io
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError:
        return None
    if im is None:
        try:
            im = load_image(src, timeout)
        except Exception:
            return None
    w, h = im.size
    # the badge sits in a bottom corner; whole image last
    for crop in (im.crop((0, int(h * 0.78), int(w * 0.42), h)), im.crop((int(w * 0.58), int(h * 0.78), w, h)), im):
        g = ImageOps.grayscale(crop).resize((crop.width * 3, crop.height * 3))
        for img in (g, ImageOps.autocontrast(g).point(lambda p: 255 if p > 150 else 0)):
            try:
                text = pytesseract.image_to_string(img, config="--psm 6")
            except Exception:
                return None
            found = (re.findall(r"[£€]\s?(\d{2,3})\s?[.,]\s?(\d{2})", text)
                     or re.findall(r"(?<!\d)(\d{2,3})[.,](\d{2})(?!\d)", text))
            if found:
                vals = set()
                for a, b in found:
                    vals.add(float(f"{a}.{b}"))
                    if len(a) == 3:
                        vals.add(float(f"{a[1:]}.{b}"))  # "£" or a stray letter read as a digit: "847.99" is £47.99
                    if b[0] == "9" and b != "99":
                        vals.add(float(f"{a[-2:] if len(a) == 3 else a}.99"))  # last 9 misread: "49.95" is £49.99
                # gift packs and kits cost £10–£200: "6.69" is a cut-off "£46.69" (badge text "2 shirts only" next to it)
                vals = sorted(v for v in vals if 10 <= v < 200)
                if vals:
                    return vals
    return []


def fetch_variations(base_url, store, delay=0.3):
    """SKU / price / attributes of every variation the public API shows (disabled or hidden variations are not
    visible without an API key)."""
    out = []
    for v in store.get("variations") or []:
        try:
            text, _ = http_get(f"{base_url}/wp-json/wc/store/v1/products/{v['id']}", retry_waits=(20, 60))
            q = json.loads(text)
            out.append({"id": v["id"], "sku": q.get("sku") or "", "price": (q.get("prices") or {}).get("price"),
                        "attributes": v.get("attributes") or [], "in_stock": q.get("is_in_stock")})
        except Exception:
            out.append({"id": v["id"], "sku": None, "price": None, "attributes": v.get("attributes") or []})
        time.sleep(min(delay, 1.0))
    return out


def cached(site, product_id):
    path = CACHE_DIR / site / f"{product_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def prefetch_store(base_url, ids):
    """Store API data for many products in one request per 100 (fewer requests = fewer firewall blocks).

    Out-of-stock products are hidden from the list endpoint; fetch_product gets those one by one.
    """
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 100):
        chunk = ",".join(str(x) for x in ids[i:i + 100])
        text, _ = http_get(f"{base_url}/wp-json/wc/store/v1/products?include={chunk}&per_page=100",
                           retry_waits=(20, 60))
        for p in json.loads(text):
            out[p["id"]] = p
    return out




def safe_url(url):
    """Image file names can contain "–" or accents: percent-encode them (keep what is already encoded)."""
    return urllib.parse.quote(url, safe=":/?&=%#+,;@~")


def fetch_text(url, timeout=40):
    """Full page as text (only used where the <head> is not enough)."""
    text, _ = http_get(url, timeout=timeout, retry_waits=(20, 60))
    return text


def image_ok(src, timeout=20):
    """True if the image URL answers 200 with an image content type."""
    if not src:
        return None
    req = urllib.request.Request(safe_url(src), headers={"User-Agent": USER_AGENT, "Range": "bytes=0-1023"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 206) and resp.headers.get("Content-Type", "").startswith("image")
    except urllib.error.HTTPError as e:
        return False if e.code in (404, 410) else None  # 403/5xx: firewall/server, not proof of a broken image
    except Exception:
        return None


def fetch_product(site, base_url, product_id, url, refresh=False, delay=0.3, store=None):
    path = CACHE_DIR / site / f"{product_id}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    if store is None:
        text, _ = http_get(f"{base_url}/wp-json/wc/store/v1/products/{product_id}", retry_waits=(20, 60))
        store = json.loads(text)
    data = {"site": site, "store": store}
    page_url = url or data["store"]["permalink"]
    try:
        # Whole page: <head> for SEO, add-to-cart options (personalisation / badge labels), H1.
        full = fetch_text(page_url)
        data["page"] = parse_head(full)
        data["page"]["h1"] = parse_h1(full)
        data["page"]["options"] = parse_options(full)
        data["page"]["badges"] = parse_badges(full)
        data["page"]["body"] = parse_body(full)
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
        # Firewall (e.g. Cloudflare on CFS) blocks the page: keep the API data, skip page-based SEO checks.
        data["page"] = {"seo_title": "", "meta_description": "", "robots": "", "canonical": "", "blocked": True}
    data["variations"] = fetch_variations(base_url, data["store"], delay)
    imgs = data["store"].get("images") or []
    data["page"]["main_image_ok"] = image_ok(imgs[0].get("src")) if imgs else None
    if imgs:
        try:
            im = load_image(imgs[0].get("src"))
            data["page"]["image_colours"] = colour_print(im)
            data["page"]["image_price"] = image_price(imgs[0].get("src"), im=im)
        except Exception:
            data["page"]["image_price"] = None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(delay)  # be gentle with the sites' firewalls (RFS blocks bursts)
    return data
