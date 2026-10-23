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


def image_price(src, timeout=30):
    """Prices printed on a product photo (gift pack "SPECIAL OFFER £49.99" badge), read with OCR.
    None when OCR is not installed or the image cannot be read; [] when no price is printed."""
    try:
        import io
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        req = urllib.request.Request(src, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            im = Image.open(io.BytesIO(resp.read())).convert("RGB")
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
                return sorted({float(f"{a}.{b}") for a, b in found})
    return []


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


FREE_PIN_TEAMS = ("spain", "france", "argentina", "england", "brazil", "portugal", "scotland")


def fetch_text(url, timeout=40):
    """Full page as text (only used where the <head> is not enough)."""
    text, _ = http_get(url, timeout=timeout, retry_waits=(20, 60))
    return text


def image_ok(src, timeout=20):
    """True if the image URL answers 200 with an image content type."""
    if not src:
        return None
    req = urllib.request.Request(src, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-1023"})
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
    name = (data["store"].get("name") or "").lower()
    try:
        # Whole page: <head> for SEO, add-to-cart options (personalisation / badge labels), Free Pin text, H1.
        full = fetch_text(page_url)
        data["page"] = parse_head(full)
        data["page"]["h1"] = parse_h1(full)
        data["page"]["options"] = parse_options(full)
        data["page"]["body"] = parse_body(full)
        if site == "KFK" and any(t in name for t in FREE_PIN_TEAMS):
            team = next(t for t in FREE_PIN_TEAMS if t in name)
            data["page"]["pin_text"] = bool(re.search(rf"free\s+{team}\s+pin", full, re.I))
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
        # Firewall (e.g. Cloudflare on CFS) blocks the page: keep the API data, skip page-based SEO checks.
        data["page"] = {"seo_title": "", "meta_description": "", "robots": "", "canonical": "", "blocked": True}
    imgs = data["store"].get("images") or []
    data["page"]["main_image_ok"] = image_ok(imgs[0].get("src")) if imgs else None
    if imgs:
        data["page"]["image_price"] = image_price(imgs[0].get("src"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(delay)  # be gentle with the sites' firewalls (RFS blocks bursts)
    return data
