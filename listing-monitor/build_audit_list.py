"""List every published product whose name has a given season, as a QA input CSV.

  python build_audit_list.py --label season_2026_27_28      -> reports/<label>/new_listings_<label>.csv
then
  python qa_listings.py --label season_2026_27_28 --max-age-hours 48   (resumable)
"""

import argparse
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor

from canonical_audit import list_products
from check_new_listings import BASE_DIR, CSV_COLUMNS, REPORT_DIR

SEASON_RE = r"\b(2026(?!\s*/\s*2?7)|2026\s*/\s*(20)?27|26\s*/\s*27|2027\s*/\s*(20)?28|27\s*/\s*28)\b"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="season_2026_27_28")
    ap.add_argument("--pattern", default=SEASON_RE, help="regex on the product name")
    ap.add_argument("--sites", nargs="*")
    args = ap.parse_args(argv)
    cfg = json.loads((BASE_DIR / "config.json").read_text(encoding="utf-8"))
    sites = args.sites or list(cfg["sites"])

    def one(site):
        return site, list_products(cfg["sites"][site].rstrip("/"))

    rows = []
    with ThreadPoolExecutor(len(sites)) as ex:
        for site, prods in ex.map(one, sites):
            hit = [p for p in prods if re.search(args.pattern, p["name"], re.I)]
            print(f"{site}: {len(prods)} san pham, {len(hit)} khop")
            rows += [{"site": site, "product_id": p["id"], "name": p["name"], "url": p["url"],
                      "published_at": p["date"], "detected_by": "audit"} for p in hit]
    out = REPORT_DIR / args.label / f"new_listings_{args.label}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} listing -> {out}")


if __name__ == "__main__":
    main()
