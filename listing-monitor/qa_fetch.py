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


def fetch_product(site, base_url, product_id, url, refresh=False, delay=0.3, store=None):
    path = CACHE_DIR / site / f"{product_id}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    if store is None:
        text, _ = http_get(f"{base_url}/wp-json/wc/store/v1/products/{product_id}", retry_waits=(20, 60))
        store = json.loads(text)
    data = {"site": site, "store": store}
    data["page"] = parse_head(fetch_head(url or data["store"]["permalink"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(delay)  # be gentle with the sites' firewalls (RFS blocks bursts)
    return data
