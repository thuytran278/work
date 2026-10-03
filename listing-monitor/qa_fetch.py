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
    if site == "KFK" and any(t in name for t in FREE_PIN_TEAMS):
        # Free Pin promo text sits near add-to-cart, so the whole page is needed.
        full = fetch_text(page_url)
        data["page"] = parse_head(full)
        team = next(t for t in FREE_PIN_TEAMS if t in name)
        data["page"]["pin_text"] = bool(re.search(rf"free\s+{team}\s+pin", full, re.I))
        data["page"]["h1"] = parse_h1(full)
    else:
        try:
            data["page"] = parse_head(fetch_head(page_url))
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise
            # Firewall (e.g. Cloudflare on CFS) blocks the page: keep the API data, skip page-based SEO checks.
            data["page"] = {"seo_title": "", "meta_description": "", "robots": "", "canonical": "", "blocked": True}
    imgs = data["store"].get("images") or []
    data["page"]["main_image_ok"] = image_ok(imgs[0].get("src")) if imgs else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(delay)  # be gentle with the sites' firewalls (RFS blocks bursts)
    return data
