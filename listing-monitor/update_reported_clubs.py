"""Reads the Reported Club Status sheet (sheet "General") into data/reported_clubs.json, which the daily QA uses
to flag live listings of reported teams on all 4 sites.

    python update_reported_clubs.py "Reported Club Status.xlsx"

Run it again whenever the sheet changes, then commit data/reported_clubs.json.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import openpyxl

BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "data" / "reported_clubs.json"
# Status column of each site in sheet "General" (0-based)
COLUMNS = {"KFK": 1, "RFS": 5, "RFK": 9, "CFS": 17}
# Brand rows, not teams: can't be matched from a product name
BRAND_ROWS = re.compile(r"^(nike|adidas|puma|others\b.*|nike logo|adidas logo|adidas socks)$", re.I)


def parse_label(label):
    """'Atletico Madrid (Nike)' -> team + scope. Scopes seen in the sheet: 'Retro Arsenal' (retro only),
    'Liverpool 24/25' (that season only), 'Retro Portugal + Portugal 2024 + 2022' (retro + those years)."""
    team = re.sub(r"\s*\(.*?\)\s*$", "", label).strip()
    brand = (re.search(r"\(([^)]*)\)\s*$", label) or [None, ""])[1]
    scope = {"retro": False, "years": [], "seasons": []}
    if "+" in team:
        parts = [p.strip() for p in team.split("+")]
        team = re.sub(r"(?i)^retro\s+", "", parts[0])
        scope["retro"] = parts[0].lower().startswith("retro")
        scope["years"] = [y for p in parts[1:] for y in re.findall(r"\b(?:19|20)\d{2}\b", p)]
    elif team.lower().startswith("retro "):
        team, scope["retro"] = team[6:].strip(), True
    else:
        m = re.match(r"(.+?)\s+(\d{2}/\d{2})$", team)
        if m:
            team, scope["seasons"] = m.group(1), [m.group(2)]
    team = {"Man United": "Manchester United"}.get(team, team)
    return team, brand, scope


def read_sheet(path):
    ws = openpyxl.load_workbook(path, data_only=True)["General"]
    teams = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        label = str(row[0] or "").strip()
        status = {s: str(row[c]).strip() for s, c in COLUMNS.items() if row[c] and str(row[c]).strip()}
        if not label or not status or BRAND_ROWS.match(label):
            continue
        team, brand, scope = parse_label(label)
        teams.append({"label": label, "team": team, "brand": brand, "scope": scope, "status": status})
    return teams


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("xlsx", help="Reported Club Status .xlsx")
    args = ap.parse_args()
    teams = read_sheet(args.xlsx)
    if not teams:
        sys.exit("Không đọc được đội nào từ sheet 'General'")
    OUT.write_text(json.dumps({"updated": date.today().isoformat(), "source": Path(args.xlsx).name, "teams": teams},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã lưu {len(teams)} đội vào {OUT}")


if __name__ == "__main__":
    main()
