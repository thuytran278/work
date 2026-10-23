"""Add the main-photo colour make-up to cached listings that do not have it yet (resumable).

  python backfill_photo_colours.py --label season_2026_27_28
"""

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor

import qa_fetch
from check_new_listings import REPORT_DIR


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    args = ap.parse_args(argv)
    rows = list(csv.DictReader((REPORT_DIR / args.label / f"new_listings_{args.label}.csv").open(encoding="utf-8-sig")))
    by_site = {}
    for r in rows:
        by_site.setdefault(r["site"], []).append(r["product_id"])

    def run(site):
        done = 0
        for pid in by_site[site]:
            path = qa_fetch.CACHE_DIR / site / f"{pid}.json"
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            page, imgs = d.setdefault("page", {}), d["store"].get("images") or []
            if page.get("image_colours") or not imgs:
                continue
            try:
                page["image_colours"] = qa_fetch.colour_print(qa_fetch.load_image(imgs[0]["src"]))
            except Exception:
                continue
            path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            done += 1
            time.sleep(0.5 if site == "RFS" else 0.1)
        return site, done

    with ThreadPoolExecutor(len(by_site)) as ex:
        for site, n in ex.map(run, list(by_site)):
            print(site, n, flush=True)


if __name__ == "__main__":
    main()
