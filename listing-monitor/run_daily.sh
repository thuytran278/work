#!/bin/sh
# Chay check listing moi + QA cho ngay UK vua ket thuc (chay buoi sang gio VN), xong tu mo file Excel.
# Mac: chay "sh run_daily.sh" trong Terminal (hoac dat lich, xem HUONG_DAN_MAY_TINH.md).
cd "$(dirname "$0")" || exit 1
python3 check_new_listings.py --yesterday && python3 qa_listings.py --yesterday --refresh --open
