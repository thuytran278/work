"""Check which new listings went live on each website, without an API key.

Two public sources are combined:
  1. RSS feed  (/feed/?post_type=product)  -> exact publish date of each product.
  2. Store API (/wp-json/wc/store/v1/products) -> list of live product IDs,
     compared with the list saved on the previous run to catch anything the
     feed missed (feed disabled, cached, or too many products in one day).

Usage:
  python check_new_listings.py                 # today (UK time)
  python check_new_listings.py --date 2026-09-25
  python check_new_listings.py --sites KFK RFS
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "data" / "state"
REPORT_DIR = BASE_DIR / "reports"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
CSV_COLUMNS = [
    "site", "product_id", "sku", "name", "url", "categories",
    "published_at", "detected_by",
]


def get_tz(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        print(f"[!] Khong doc duoc timezone {name}, dung UTC. "
              "Tren Windows chay: pip install tzdata")
        return timezone.utc


def http_get(url, timeout=30, retry_waits=(10, 30)):
    """Return (body_text, headers). Raises on HTTP / network error.

    Retries on 403/429/5xx: some sites' firewalls block bursts of requests.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for wait in (*retry_waits, None):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # Some sites prepend a UTF-8 BOM, which breaks json / xml parsing.
                return resp.read().decode("utf-8-sig", errors="replace"), resp.headers
        except urllib.error.HTTPError as e:
            if wait is None or not (e.code in (403, 429) or e.code >= 500):
                raise
            time.sleep(wait)


# ---------------------------------------------------------------- RSS feed

class RssDisabled(Exception):
    pass


def parse_rss(xml_text, tz):
    """Return list of {product_id, name, url, published_at(datetime)}."""
    items = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        guid = item.findtext("guid") or ""
        m = re.search(r"[?&]p=(\d+)", guid)
        pub = item.findtext("pubDate")
        items.append({
            "product_id": int(m.group(1)) if m else None,
            "name": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "published_at": parsedate_to_datetime(pub).astimezone(tz) if pub else None,
        })
    return items


def fetch_rss_for_date(base_url, target, tz, max_pages, fetch=http_get):
    """Products whose publish date (site timezone) equals target.

    Feed is newest first, so stop once we reach an item older than target.
    """
    found = []
    for page in range(1, max_pages + 1):
        url = f"{base_url}/feed/?post_type=product"
        if page > 1:
            url += f"&paged={page}"
        try:
            text, _ = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404 and page > 1:  # no more pages
                break
            raise
        if "<rss" not in text[:500]:
            # Feed disabled: WordPress redirects to the homepage (HTML).
            raise RssDisabled("RSS feed bi tat tren site (chi dung so sanh danh sach)")
        items = parse_rss(text, tz)
        if not items:
            break
        for it in items:
            if it["published_at"] and it["published_at"].date() == target:
                found.append(it)
        oldest = min((i["published_at"] for i in items if i["published_at"]), default=None)
        if oldest is None or oldest.date() < target:
            break
    return found


# --------------------------------------------------------------- Store API

def fetch_store_products(base_url, known_ids, max_pages, fetch=http_get):
    """Newest products from the public Store API.

    Stops early once a whole page is already known (nothing newer beyond it).
    """
    products = []
    for page in range(1, max_pages + 1):
        url = (f"{base_url}/wp-json/wc/store/v1/products"
               f"?orderby=date&order=desc&per_page=100&page={page}")
        text, headers = fetch(url)
        batch = json.loads(text)
        if not batch:
            break
        products.extend(batch)
        if known_ids and all(p["id"] in known_ids for p in batch):
            break
        total_pages = int(headers.get("X-WP-TotalPages") or page)
        if page >= total_pages:
            break
    return products


def load_state(site):
    path = STATE_DIR / f"{site}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_state(site, known_ids, now):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{site}.json"
    path.write_text(json.dumps({
        "last_run": now.isoformat(timespec="seconds"),
        "known_ids": sorted(known_ids),
    }), encoding="utf-8")


# ------------------------------------------------------------------ merge

def check_site(site, base_url, target, tz, cfg, use_diff, fetch=http_get):
    """Return (rows, notes) for one site."""
    notes = []
    by_id = {}

    # 1. RSS
    try:
        for it in fetch_rss_for_date(base_url, target, tz, cfg["rss_max_pages"], fetch):
            key = it["product_id"] or it["url"]
            by_id[key] = {
                "site": site, "product_id": it["product_id"] or "", "sku": "",
                "name": it["name"], "url": it["url"], "categories": "",
                "published_at": it["published_at"].strftime("%Y-%m-%d %H:%M"),
                "detected_by": "rss",
            }
    except RssDisabled as e:
        notes.append(str(e))
    except Exception as e:
        notes.append(f"RSS loi: {e}")

    # 2. Store API (always fetched: used for diff + to fill SKU / category)
    state = load_state(site)
    known = set(state["known_ids"]) if state else set()
    try:
        products = fetch_store_products(base_url, known, cfg["store_api_max_pages"], fetch)
    except Exception as e:
        products = None
        notes.append(f"Store API loi: {e}")

    if products is not None:
        store = {p["id"]: p for p in products}
        # fill details for RSS rows
        for key, row in by_id.items():
            p = store.get(key)
            if p:
                row["sku"] = p.get("sku", "")
                row["categories"] = ", ".join(c["name"] for c in p.get("categories", []))
                row["detected_by"] = "rss+diff" if use_diff and state and key not in known else "rss"

        if use_diff:
            if state is None:
                notes.append("Lan chay dau: da luu danh sach goc, tu mai moi so sanh duoc.")
            else:
                for pid, p in store.items():
                    if pid not in known and pid not in by_id:
                        by_id[pid] = {
                            "site": site, "product_id": pid, "sku": p.get("sku", ""),
                            "name": p.get("name", ""), "url": p.get("permalink", ""),
                            "categories": ", ".join(c["name"] for c in p.get("categories", [])),
                            "published_at": "",
                            "detected_by": "diff",
                        }
            save_state(site, known | set(store), datetime.now(tz))

    return list(by_id.values()), notes


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check new listings per website.")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today, UK time)")
    ap.add_argument("--sites", nargs="*", help="e.g. KFK RFS (default: all)")
    ap.add_argument("--config", default=str(BASE_DIR / "config.json"))
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tz = get_tz(cfg.get("timezone", "Europe/London"))
    today = datetime.now(tz).date()
    target = date.fromisoformat(args.date) if args.date else today
    # Diff = "new since last run", only meaningful when checking today.
    use_diff = target == today

    sites = {k: v.rstrip("/") for k, v in cfg["sites"].items()
             if not args.sites or k in args.sites}

    all_rows, lines = [], [f"LISTING MOI NGAY {target.isoformat()}", ""]
    for site, url in sites.items():
        rows, notes = check_site(site, url, target, tz, cfg, use_diff)
        all_rows.extend(rows)
        status = f"{len(rows)} listing moi" if rows else "khong co listing moi"
        if notes and not rows and any("loi" in n for n in notes):
            status = "KHONG KIEM TRA DUOC"
        lines.append(f"{site}: {status}")
        for r in rows:
            lines.append(f"   - {r['name']}  [{r['sku'] or '-'}]  {r['url']}")
        for n in notes:
            lines.append(f"   (!) {n}")
    lines += ["", f"Tong: {len(all_rows)} listing moi"]
    if not use_diff:
        lines.append("(Ngay trong qua khu: chi dung RSS, khong so sanh danh sach)")

    out_dir = REPORT_DIR / target.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"new_listings_{target.isoformat()}.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel reads accents
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(all_rows)
    summary = "\n".join(lines)
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")

    print(summary)
    print(f"\nFile chi tiet: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
