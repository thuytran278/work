# Listing Monitor: tài liệu dự án và nhật ký hằng ngày

Theo dõi listing mới trên 4 website (KFK, RFS, RFK, CFS) và QA sâu từng listing, mỗi ngày một lần.

- Repo: `thuytran278/work`, branch `claude/gifted-tesla-l4ekcx`, thư mục `listing-monitor/`
- Người phụ trách: Clara
- Cập nhật lần cuối: 2/10/2026

> **Quy ước:** mỗi lần chạy routine hoặc thay đổi quy tắc đều phải ghi thêm vào mục **7. Nhật ký hằng ngày** và **8. Changelog**. Không xoá các mục cũ.

---

## 1. Tổng quan

| Thành phần | File | Việc làm |
|---|---|---|
| Tìm listing mới | `check_new_listings.py` | Lấy listing đăng trong ngày hoặc trong khoảng ngày |
| Tải dữ liệu listing | `qa_fetch.py` | Store API (tên, SKU, mô tả, attribute, ảnh, giá, tồn kho) + `<head>` trang (SEO title, meta, canonical, robots) |
| Quy tắc gốc | `qa_rules.py` | Các check theo SOP listing/SEO |
| Quy tắc bổ sung | `qa_rules_extra.py` | Part A: KFK Master File · Part B: case mới · Part C: football-qa-tools commit 2/10 · Part D: SEO tên cầu thủ |
| Xuất báo cáo | `qa_listings.py` | Excel mỗi web 1 sheet + `qa_summary.txt` |
| Audit canonical | `canonical_audit.py` | Check canonical cho toàn bộ listing 26/27 |
| Cấu hình | `config.json` | URL 4 site, timezone UK, độ trễ request (RFS 3 giây) |
| Test | `tests/` | `python3 -m unittest discover -s tests` |

**Nguồn dữ liệu (công khai, không cần API key):**
- `/wp-json/wp/v2/product`: ngày đăng chính xác, lọc theo khoảng ngày (nguồn chính)
- `/feed/?post_type=product`: dự phòng (RFS và CFS đã tắt feed)
- `/wp-json/wc/store/v1/products`: dữ liệu sản phẩm, và so danh sách với lần chạy trước (`data/state/`)
- Trang sản phẩm: chỉ đọc `<head>`. Riêng KFK của 7 đội Free Pin thì đọc toàn trang.

## 2. Cách chạy

```
cd listing-monitor
python3 check_new_listings.py                                  # listing mới hôm nay (giờ UK)
python3 check_new_listings.py --from 2026-09-01 --to 2026-10-02 # khoảng ngày
python3 qa_listings.py                                          # QA listing mới hôm nay
python3 qa_listings.py --from 2026-09-01 --max-age-hours 6      # QA khoảng ngày, chạy tiếp được nếu bị dừng
python3 canonical_audit.py                                      # audit canonical toàn bộ listing 26/27
```

Kết quả nằm trong `reports/<ngày>/`:
- `new_listings_<ngày>.csv`
- `summary.txt`
- `qa_<ngày>.xlsx`: sheet **Tổng quan**, **KFK / RFS / RFK / CFS** (có cột "Người sửa" và "Đã sửa"), **Cần xác nhận**
- `qa_summary.txt`

## 3. Routine hằng ngày

- Tên: **Daily new listing check + QA** (trigger `trig_013bP3UC5Sjkocr5bMWoPiBx`)
- Giờ chạy: **23:24 giờ UK**, tức khoảng 5:24 sáng giờ Việt Nam
- Các bước:
  1. Pull branch
  2. `check_new_listings.py`
  3. `qa_listings.py --refresh` (nếu có listing mới)
  4. Commit `data/state/` và `reports/<ngày>/`, rồi push
  5. Báo Clara: số listing mới, lỗi Cao, file Excel
  6. **Ghi 1 dòng vào mục 7 của file này**

## 4. Danh sách check

Mức độ: **Cao** = sai thông tin, gây confuse khách hoặc Google · **TB** = cần sửa · **Thấp** = nên sửa.
Lỗi xuất hiện trên ≥ 50% listing của 1 site (tối thiểu 5 listing) được gom thành **lỗi template**. Lỗi Cao không bao giờ bị gom.

| Nhóm | Check chính | Nguồn |
|---|---|---|
| Sai đối tượng | SKU (AD/KD/WM/ADK/BABY) so với tên, Gender/Age, size, SEO, alt ảnh; bảng size trong description có size không bán; size chart sai đối tượng | SOP, C |
| Sai loại Shirt/Kit | SEO/description dùng sai Shirt hoặc Kit; KFK: kit không ghi "shirt" và ngược lại | SOP, A |
| Sai Home/Away/Third | Tên so với SKU, Kit Type, SEO, description, short description, alt và tên file ảnh, category | SOP, A, C |
| Sai team | Attribute so với tên/SEO/category (nhận ra tên né thương hiệu); ảnh mang tên team khác | SOP, C |
| Sai season | SKU, attribute, SEO, description (24/25, 25/26), alt, tag, slug | SOP, A, B |
| Sai cầu thủ | Thiếu player attribute/category; còn Personalisation; SKU `No` nhưng có tên cầu thủ; số áo lệch | SOP, A, C |
| SEO tên cầu thủ | Tên cầu thủ ở cuối tên; ở sau ký tự 45 của SEO title; H1 thiếu cầu thủ hoặc Shirt/Kit; ≥ 5 URL cùng mẫu áo | D |
| Sai tất | With/No socks: tên so với attribute, description và meta | SOP, C |
| Sleeve | Chỉ báo khi mâu thuẫn với Long Sleeve (tên/SKU LS/LV/ảnh) | SOP (Clara 27/9) |
| Words to Avoid | Bảng SOP + bảng KFK; KFK cấm tuyệt đối official, authentic, real, identical, genuine, replica | SOP, A |
| Lỗi template / copy | `%focuskw%`, "kit kit", "Is this the real…", lặp từ, 3 chữ liền | A, C |
| SEO | Canonical sai, noindex (trừ gift pack), title/meta trống, quá dài, không khớp sản phẩm, trùng | SOP, A |
| Kho / Giá | Hết hàng, giá 0, giá KFK lệch bảng giá Master File, Budget, giá trong description lệch giá bán | A, C |
| Ảnh | Không có ảnh, alt trống hoặc trùng, < 3 ảnh, ảnh chính lỗi, màu ảnh mâu thuẫn description | B, C |
| SKU | Sai format, đuôi `-1`, ký tự HTML, dấu cách hoặc ký tự lạ (Google Merchant) | SOP, A, C |
| URL / Slug | Slug có season cũ hoặc sai loại áo | B |
| Club bị report (KFK) | Listing live trong khi sheet ghi Private/Draft; Arsenal chỉ bán bundle | A |
| Free Pin (KFK) | 7 đội phải có "FREE [TEAM] PIN" | A |
| Category / Tag | League cha, National Team, World Cup 2026, Players; tag/category của team hoặc season khác | A |

## 5. Quyết định đã xác nhận

| Ngày | Quyết định |
|---|---|
| 27/9 | **ADK = Adult Kit** (áo + quần người lớn), không phải combo Adult + Kid |
| 27/9 | **Gift pack để noindex là cố ý**, không báo lỗi |
| 27/9 | Listing in chữ **CHAMPIONS 26 / WINNERS 26** không cần player attribute/category |
| 27/9 | **"Short sleeve"** trong description là OK nếu khớp ảnh. Chỉ báo khi mâu thuẫn với Long Sleeve |
| 2/10 | **Format tên listing cầu thủ (CFS)**: tên cầu thủ ngay sau CLB, giữ nguyên slug (xem mục 6) |

## 6. Case nghiên cứu: CFS mất khoảng 75% traffic từ 20/8/2026

**Hiện tượng (GSC):** khoảng 1.000 click/ngày trong tháng 7, giảm dần từ cuối tháng 7, rồi rơi xuống khoảng 150 click/ngày quanh 19–21/8, và vẫn chưa hồi phục.

**Dữ liệu từ site (2/10):**
- Tháng 6–7 thêm 711 listing (bình thường khoảng 100/tháng). Site tăng từ khoảng 2.650 lên **4.010 sản phẩm**.
- Tuần **17–23/8**: 182 listing mới, trong đó **107 listing cầu thủ**, đúng tuần traffic rơi mạnh nhất.
- **382 listing cầu thủ** dạng "… – KANE 9", chia cho 176 mẫu áo gốc. 28 mẫu áo có ≥ 5 URL (Liverpool Away / Man City Away có 10–11 URL).
- Description bản cầu thủ giống nhau 85–86% và giống bản gốc 76%. Ảnh dùng chung, chỉ khác ảnh mặt sau.
- H1 không có tên cầu thủ (ví dụ "Bayern Munich Away Men 2026/27"), nên mọi URL của cùng mẫu áo có H1 trùng nhau.
- SEO title có tên cầu thủ nhưng ở cuối (sau ký tự 70–80), nên bị Google cắt mất.
- 12/9: 3.426 sản phẩm bị sửa cùng ngày. Việc này xảy ra **sau** khi traffic đã giảm, nên không phải nguyên nhân.
- Cloudflare của CFS đang chặn bot ("Attention Required"). Cần kiểm tra có chặn cả Googlebot không.

**Nhận định:** nhiều URL gần trùng làm Google không biết xếp hạng trang nào (ăn thịt từ khoá), bỏ bớt trang khỏi index và hạ chất lượng cả domain. Cú rơi khoảng 75% trong 1 ngày nên cần loại trừ thêm: Google update quanh 20/8, Cloudflare chặn Googlebot, manual action hoặc DMCA, index bloat.

**Format đã chốt (Clara 2/10):**

| Trường | Format | Ví dụ |
|---|---|---|
| Product name | `[Club] [PLAYER] [Số] [Home/Away/Third] [Men/Kids] Cheap Football [Shirt/Kit] [Season]` | Bayern Munich KANE 9 Away Men Cheap Football Shirt 2026/27 |
| H1 | `[Club] [PLAYER] [Số] [Home/Away/Third] [Men/Kids] [Shirt/Kit] [Season]` | Bayern Munich KANE 9 Away Men Shirt 2026/27 |
| SEO title | H1 + ` \| Cheap Football Shirts` (cầu thủ trong 45 ký tự đầu) | Bayern Munich KANE 9 Away Men Shirt 2026/27 \| Cheap Football Shirts |
| Slug | **Giữ nguyên** | |
| Bản Kids | Men → Kids, Shirt → Kit | Bayern Munich KANE 9 Away Kids Kit 2026/27 |

**Kế hoạch xử lý:**
1. Kiểm tra trong GSC: Manual actions, Crawl stats (403/5xx quanh 20/8), Pages (Duplicate / Crawled not indexed), Google Search Status Dashboard, lumendatabase.org.
2. Tạm dừng đăng hàng loạt listing cầu thủ.
3. Đổi tên theo đợt khoảng 50 listing/tuần, ưu tiên cầu thủ có impression. Chờ 1–2 tuần, so sánh với nhóm chưa đổi rồi mới tăng tốc. Lý do: đo được hiệu quả, sai thì chỉ sai ít, giữ traffic còn lại, không đổi nhiều thứ cùng lúc.
4. Cầu thủ 90 ngày không có impression: noindex hoặc canonical về listing gốc.
5. Sửa template H1 để hiện tên cầu thủ và Shirt/Kit.

**Check tự động (Part D):** "SEO tên cầu thủ" gồm cầu thủ ở cuối tên, cầu thủ nằm sau ký tự 45 của SEO title, H1 thiếu cầu thủ hoặc Shirt/Kit (khi tải được toàn trang), và ≥ 5 URL cùng mẫu áo.
File tham khảo: `CFS_listing_cau_thu_trung_lap.xlsx` (382 listing, 176 nhóm), gửi Clara ngày 2/10.

## 7. Nhật ký hằng ngày

Định dạng: `Ngày | Listing mới (KFK/RFS/RFK/CFS) | Listing có lỗi Cao | Ghi chú`

| Ngày | Listing mới | Lỗi Cao | Ghi chú |
|---|---|---|---|
| 26/9 | 2 / 2 / 0 / 13 | CFS 1 | Lần chạy đầu. Man City Away Adult (CFS) dùng size chart Kids |
| 27/9 | 1 / 5 / 0 / 0 | RFS 5 | 5 listing RFS DONNARUMMA 1 có canonical trỏ về trang mùa cũ |
| 28/9 | 0 / 0 / 0 / 0 | – | Không có listing mới |
| 29/9 | 1 / 1 / 0 / 0 | RFS 1 | Crystal Palace Away (RFS): SEO và canonical của bản Home; KFK "(Witth Socks)" |
| 30/9 | 0 / 48 / 0 / 25 | RFS 4, CFS 1 | 46 listing cũ vừa hiện lại. Retro RFS sai Home/Away; Wales Kids (CFS) dùng size chart Adult |
| 1/10 | 10 / 0 / 1 / 0 | – | Không có lỗi Cao |
| 2/10 | 0 / 0 / 8 / 1 | – | RFK 8 listing không có lỗi Cao. CFS 1 listing (Argentina MESSI 10 Kids) không check được: Cloudflare CFS chặn (403) |

**Báo cáo tổng hợp:**

| Ngày chạy | Phạm vi | Kết quả |
|---|---|---|
| 26/9 | 26/8–26/9, 836 listing | 77 listing lỗi Cao. KFK: 13 canonical về mùa cũ, gift pack noindex |
| 29/9 | 26/8–29/9, 856 listing (tải mới) | Chưa listing lỗi Cao nào được sửa. Mỗi web 1 sheet |
| 1/10 | Canonical audit, 2.339 listing 26/27 | KFK 7 (Schalke và Stoke trỏ về Real Oviedo 2023-24), RFS 1 (Crystal Palace Away) |
| 2/10 | 1/9–2/10, 785 listing (tải mới, đủ bộ check A–C) | Cao: KFK 16, RFS 16, RFK 5, CFS 5 |

## 8. Changelog

| Ngày | Thay đổi |
|---|---|
| 26/9 | Tạo tool: tìm listing mới (RSS + Store API), routine 23:24 UK |
| 26/9 | Chuyển sang WP REST làm nguồn chính; xử lý BOM, feed bị tắt, tường lửa chặn tạm thời |
| 26/9 | QA sâu: `qa_rules.py`, Excel, gom lỗi template, tiếng Việt có dấu |
| 27/9 | Áp dụng quyết định của Clara (ADK, gift pack noindex, CHAMPIONS, short sleeve) |
| 27/9 | Lỗi Cao không bị gom vào nhóm template |
| 29/9 | Excel tách mỗi web 1 sheet, thêm cột Người sửa / Đã sửa |
| 1/10 | `canonical_audit.py` (lưu tiến độ, chạy tiếp được nếu bị dừng) |
| 2/10 | Part A–B: quy tắc KFK Master File (football-qa-tools) + case mới (chính tả, slug, tag team khác, ảnh lỗi…) |
| 2/10 | Part C: các check trong commit `c3c1e3c` của football-qa-tools (giá trong description, Main colours, ảnh sai team/loại áo/đối tượng/màu, bảng size, socks, category kit type, lỗi đánh máy, SKU Google, size chart) |
| 2/10 | Part D: SEO tên cầu thủ (case CFS); `--max-age-hours` cho QA |

## 9. Hạn chế đã biết và câu hỏi còn mở

- **Cloudflare CFS** chặn tool đọc trang HTML (từ 2/10). SEO title, meta, canonical và H1 của CFS có thể không cập nhật được. Cần whitelist IP hoặc tắt chặn cho tool.
- **Free Pin (KFK):** HTML không có "FREE [TEAM] PIN". Khuyến mãi còn chạy không, hay chữ được hiển thị bằng JavaScript?
- **Bay^_^rn / P^_^SG:** sheet Reported Club ghi Private, nhưng listing vẫn live (có noindex). Có phải team giữ live và để noindex không?
- **Wales 2027** (KFK, CFS): năm 2027 có đúng không? SOP ghi đội tuyển dùng 2026.
- **Trustpilot 4.9** trong short description của KFK, RFS, RFK: giữ hay bỏ?
- Chưa làm được: so màu thật trong ảnh (phân tích pixel); check 6 tab sản phẩm của RFS; H1 của CFS (bị Cloudflare chặn).
- Tool chỉ thấy listing đã publish, không thấy draft hay private.
