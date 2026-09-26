"""Check which new listings went live on each website, without an API key.

Public sources, combined:
  1. WP REST (/wp-json/wp/v2/product?after=&before=) -> exact publish date,
     filtered by date range. Main source.
  2. RSS feed (/feed/?post_type=product) -> fallback when WP REST fails.
  3. Store API (/wp-json/wc/store/v1/products) -> list of live product IDs,
     compared with the list saved on the previous run to catch anything the
     dated sources missed. Also used to fill SKU / categories.

Usage:
  python check_new_listings.py                                  # today (UK time)
  python check_new_listings.py --date 2026-09-25
  python check_new_listings.py --from 2026-08-26 --to 2026-09-26
  python check_new_listings.py --sites KFK RFS
"""

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
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
    "site", "product_id", "sku", "name", "url", "categories", "in_stock",
    "published_at", "detected_by",
]
MAX_LISTED_PER_SITE = 30  # longer lists: see the CSV


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


def make_row(site, pid, name, url, published_at, source):
    return {
        "site": site, "product_id": pid or "", "sku": "", "name": name,
        "url": url, "categories": "", "in_stock": "",
        "published_at": published_at.strftime("%Y-%m-%d %H:%M") if published_at else "",
        "detected_by": source,
    }


# ---------------------------------------------------------------- WP REST

def fetch_wp_products(base_url, start, end, max_pages, fetch=http_get):
    """Products published between start and end (inclusive, site local time)."""
    found = []
    after = f"{(start - timedelta(days=1)).isoformat()}T23:59:59"
    before = f"{(end + timedelta(days=1)).isoformat()}T00:00:00"
    for page in range(1, max_pages + 1):
        url = (f"{base_url}/wp-json/wp/v2/product?after={after}&before={before}"
               f"&per_page=100&page={page}&orderby=date&order=desc"
               f"&_fields=id,date,link,title")
        text, headers = fetch(url)
        batch = json.loads(text)
        for p in batch:
            found.append({
                "product_id": p["id"],
                "name": html.unescape(p.get("title", {}).get("rendered", "")),
                "url": p.get("link", ""),
                "published_at": datetime.fromisoformat(p["date"]),
            })
        if len(batch) < 100 or page >= int(headers.get("X-WP-TotalPages") or page):
            break
    return found


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


def fetch_rss_for_range(base_url, start, end, tz, max_pages, fetch=http_get):
    """Products whose publish date (site timezone) is between start and end.

    Feed is newest first, so stop once we reach an item older than start.
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
            raise RssDisabled("RSS feed bi tat tren site")
        items = parse_rss(text, tz)
        if not items:
            break
        for it in items:
            if it["published_at"] and start <= it["published_at"].date() <= end:
                found.append(it)
        oldest = min((i["published_at"] for i in items if i["published_at"]), default=None)
        if oldest is None or oldest.date() < start:
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


def fetch_store_by_ids(base_url, ids, fetch=http_get):
    """Store API details (SKU, categories) for specific product IDs."""
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 100):
        chunk = ",".join(str(x) for x in ids[i:i + 100])
        text, _ = fetch(f"{base_url}/wp-json/wc/store/v1/products?include={chunk}&per_page=100")
        for p in json.loads(text):
            out[p["id"]] = p
    # Out-of-stock products are hidden from the list endpoint: fetch one by one.
    for pid in ids:
        if pid not in out:
            text, _ = fetch(f"{base_url}/wp-json/wc/store/v1/products/{pid}")
            out[pid] = json.loads(text)
    return out


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

def check_site(site, base_url, start, end, tz, cfg, use_diff, fetch=http_get):
    """Return (rows, notes) for one site. rows sorted newest first."""
    notes = []
    by_id = {}
    dated_ok = False

    # 1. WP REST (main), 2. RSS only if WP REST failed
    try:
        for it in fetch_wp_products(base_url, start, end, cfg["wp_max_pages"], fetch):
            by_id[it["product_id"]] = make_row(
                site, it["product_id"], it["name"], it["url"], it["published_at"], "wp")
        dated_ok = True
    except Exception as e:
        notes.append(f"WP REST loi: {e}")
        try:
            for it in fetch_rss_for_range(base_url, start, end, tz, cfg["rss_max_pages"], fetch):
                key = it["product_id"] or it["url"]
                by_id[key] = make_row(
                    site, it["product_id"], it["name"], it["url"], it["published_at"], "rss")
            dated_ok = True
        except RssDisabled as e2:
            notes.append(str(e2))
        except Exception as e2:
            notes.append(f"RSS loi: {e2}")

    # 3. Store API diff (only when the range ends today)
    store = {}
    if use_diff:
        state = load_state(site)
        known = set(state["known_ids"]) if state else set()
        try:
            store = {p["id"]: p for p in fetch_store_products(
                base_url, known, cfg["store_api_max_pages"], fetch)}
            if state is None:
                notes.append("Lan chay dau: da luu danh sach goc de so sanh tu lan sau.")
            else:
                for pid, p in store.items():
                    if pid in known:
                        continue
                    if pid in by_id:
                        by_id[pid]["detected_by"] += "+diff"
                    else:
                        by_id[pid] = make_row(site, pid, p.get("name", ""),
                                              p.get("permalink", ""), None, "diff")
            save_state(site, known | set(store), datetime.now(tz))
        except Exception as e:
            notes.append(f"Store API loi: {e}")
            if not dated_ok:
                notes.append("KHONG KIEM TRA DUOC")

    elif not dated_ok:
        notes.append("KHONG KIEM TRA DUOC")

    # 4. Fill SKU / categories
    missing = [k for k in by_id if isinstance(k, int) and k not in store]
    try:
        store.update(fetch_store_by_ids(base_url, missing, fetch) if missing else {})
    except Exception as e:
        notes.append(f"Khong lay duoc SKU/category: {e}")
    for key, row in by_id.items():
        p = store.get(key)
        if p:
            row["sku"] = p.get("sku", "")
            row["categories"] = ", ".join(html.unescape(c["name"]) for c in p.get("categories", []))
            row["in_stock"] = "yes" if p.get("is_in_stock", True) else "NO"

    rows = sorted(by_id.values(), key=lambda r: r["published_at"], reverse=True)
    return rows, notes


def build_summary(start, end, results, use_diff):
    title = (f"LISTING MOI NGAY {start.isoformat()}" if start == end
             else f"LISTING MOI TU {start.isoformat()} DEN {end.isoformat()}")
    lines, total = [title, ""], 0
    for site, (rows, notes) in results.items():
        total += len(rows)
        if "KHONG KIEM TRA DUOC" in notes:
            status = "KHONG KIEM TRA DUOC"
        else:
            status = f"{len(rows)} listing moi" if rows else "khong co listing moi"
        oos = sum(1 for r in rows if r["in_stock"] == "NO")
        if oos:
            status += f" ({oos} dang HET HANG)"
        lines.append(f"{site}: {status}")
        if start != end and rows:
            per_day = Counter(r["published_at"][:10] or "(khong ro ngay)" for r in rows)
            lines.append("   Theo ngay: " + ", ".join(
                f"{d[5:] if d[0].isdigit() else d}: {n}" for d, n in sorted(per_day.items())))
        if len(rows) <= MAX_LISTED_PER_SITE:
            for r in rows:
                oos = "  [HET HANG]" if r["in_stock"] == "NO" else ""
                lines.append(f"   - {r['published_at'] or '?':16}  {r['name']}  "
                             f"[{r['sku'] or '-'}]{oos}  {r['url']}")
        else:
            lines.append(f"   (Danh sach {len(rows)} listing: xem file CSV)")
        for n in notes:
            if n != "KHONG KIEM TRA DUOC":
                lines.append(f"   (!) {n}")
    lines += ["", f"Tong: {total} listing moi"]
    if not use_diff:
        lines.append("(Khoang ngay trong qua khu: khong so sanh danh sach)")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check new listings per website.")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today, UK time)")
    ap.add_argument("--from", dest="date_from", help="YYYY-MM-DD, start of range")
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD, end of range (default: today)")
    ap.add_argument("--sites", nargs="*", help="e.g. KFK RFS (default: all)")
    ap.add_argument("--config", default=str(BASE_DIR / "config.json"))
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tz = get_tz(cfg.get("timezone", "Europe/London"))
    today = datetime.now(tz).date()
    if args.date_from:
        start = date.fromisoformat(args.date_from)
        end = date.fromisoformat(args.date_to) if args.date_to else today
    else:
        start = end = date.fromisoformat(args.date) if args.date else today
    # Diff = "new since last run", only meaningful when the range ends today.
    use_diff = end == today

    sites = {k: v.rstrip("/") for k, v in cfg["sites"].items()
             if not args.sites or k in args.sites}
    results = {site: check_site(site, url, start, end, tz, cfg, use_diff)
               for site, url in sites.items()}

    label = start.isoformat() if start == end else f"{start.isoformat()}_to_{end.isoformat()}"
    out_dir = REPORT_DIR / label
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"new_listings_{label}.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel reads accents
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for rows, _ in results.values():
            w.writerows(rows)
    summary = build_summary(start, end, results, use_diff)
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")

    print(summary)
    print(f"\nFile chi tiet: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
