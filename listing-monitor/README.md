# Listing Monitor: kiểm tra listing mới + QA lỗi mỗi ngày

Gồm 2 bước:
1. `check_new_listings.py`: tìm listing mới đăng trong ngày hoặc trong một khoảng ngày.
2. `qa_listings.py`: check sâu từng listing mới và xuất file Excel lỗi (xem mục **QA listing** bên dưới).

Script kiểm tra xem trong ngày có listing mới nào được đăng lên 4 site (KFK, RFS, RFK, CFS). **Không cần API key**, chỉ dùng dữ liệu công khai của website.

## Cách hoạt động

| Nguồn | Link | Dùng để |
|---|---|---|
| WP REST (công khai) | `/wp-json/wp/v2/product` | **Nguồn chính**: ngày giờ đăng chính xác, lọc được theo khoảng ngày |
| RSS feed | `/feed/?post_type=product` | Dự phòng khi WP REST lỗi |
| Store API (công khai) | `/wp-json/wc/store/v1/products` | So danh sách ID hôm nay với lần chạy trước để bắt listing mà 2 nguồn trên bỏ sót. Đồng thời lấy SKU và category |

Cột `detected_by` trong file CSV cho biết listing được phát hiện từ nguồn nào:
- `wp` / `rss`: có ngày đăng nằm trong khoảng ngày cần xem
- `wp+diff`: cả hai cách đều thấy
- `diff`: nguồn có ngày đăng không thấy, nhưng ID mới xuất hiện so với lần chạy trước

Cột `in_stock = NO`: listing mới đăng nhưng đang **hết hàng**, nên bị ẩn khỏi trang shop.

## Cài đặt (một lần)

1. Cài Python 3.9 trở lên từ python.org, nhớ tick **Add Python to PATH**.
2. Chỉ riêng Windows: mở Command Prompt và chạy `pip install tzdata` (để script dùng đúng giờ UK).

## Chạy

```
cd listing-monitor
python check_new_listings.py                    # hôm nay (giờ UK)
python check_new_listings.py --sites KFK RFS    # chỉ check một vài site
python check_new_listings.py --date 2026-09-25  # xem một ngày cũ
python check_new_listings.py --from 2026-08-26 --to 2026-09-26  # xem cả khoảng ngày
```

Kết quả:
- In tóm tắt ra màn hình, ví dụ `KFK: 3 listing moi`, `RFS: khong co listing moi`.
- File `reports/<ngày>/new_listings_<ngày>.csv` mở được bằng Excel, gồm các cột: site, product_id, sku, name, url, categories, published_at, detected_by.
- File `reports/<ngày>/summary.txt`: bản tóm tắt, dán thẳng vào báo cáo được.

## QA listing

```
python qa_listings.py                                   # QA listing mới hôm nay (chạy sau check_new_listings.py)
python qa_listings.py --from 2026-08-26 --to 2026-09-26 # QA cả khoảng ngày
python qa_listings.py --refresh                         # tải lại dữ liệu, bỏ qua cache
```

Cần cài thêm: `pip install openpyxl`.

Kết quả nằm trong `reports/<ngày>/`:
- `qa_<ngày>.xlsx`: gồm 3 sheet
  - **Tổng quan**: số listing lỗi theo site và theo nhóm, cùng danh sách **lỗi lặp lại do template** (xuất hiện trên ≥ 50% listing của 1 site, chỉ cần sửa template 1 lần).
  - **Lỗi chi tiết**: mỗi dòng là 1 lỗi, có mức độ (Cao / Trung bình / Thấp), vị trí, chi tiết, cách sửa, link sản phẩm và link sửa trong wp-admin. Dùng filter để lọc theo site hoặc mức độ.
  - **Cần xác nhận**: các quy tắc tool chưa chắc, cần Clara quyết.
- `qa_summary.txt`: bản tóm tắt ngắn.

Tool check những gì (chỉ dùng dữ liệu công khai: Store API + phần `<head>` của trang, tức SEO title/meta mà Rank Math xuất ra):

| Nhóm | Check |
|---|---|
| Sai đối tượng | SKU (AD/KD/WM/ADK/BABY) so với tên, attribute Gender/Age, size, SEO title/meta |
| Sai loại Shirt/Kit | Tên nói Kit nhưng SEO title/meta nói Shirt (và ngược lại); Shirt nhưng description có quần short |
| Sai Home/Away/Third | Tên so với SKU, attribute Kit Type, SEO title/meta, alt ảnh |
| Sai team | Attribute Clubs Name so với tên, SEO, category (nhận ra tên né thương hiệu như `Arsn@l`, `Lvr^_^pooI`) |
| Sai season | Tên so với SKU, attribute Season, SEO, description (season cũ 24/25, 25/26), alt ảnh |
| Sai cầu thủ | Listing cầu thủ thiếu player attribute/category, còn phần Personalisation; listing `No` nhưng có tên cầu thủ |
| Sai tất (socks) | With/No socks ở tên so với attribute và description |
| Sleeve | Nhắc "short sleeve"; Long Sleeve ở tên và SKU (LS/LV) không khớp |
| Words to Avoid | official, authentic, crest, badge, sponsor, logo, tên brand, tên sân, Trustpilot… |
| Nội dung bắt buộc | RFS: câu "Our package contains exactly…", short description đúng 3 bullet |
| SEO | Canonical trỏ sang trang khác, NOINDEX, thiếu hoặc quá dài title/meta, lỗi định dạng, trùng title/meta |
| Ảnh | Không có ảnh, thiếu hoặc trùng alt, size chart sai đối tượng |
| Kho / Giá | Hết hàng, giá 0, sản phẩm variable không có variation |

Chỉnh quy tắc trong `qa_rules.py`. Tên né thương hiệu nằm ở `TEAM_ALIASES`, Words to Avoid ở `WORDS_TO_AVOID`.

RFS chặn khi bị gọi quá dồn dập, nên `config.json` → `request_delay` để RFS nghỉ 3 giây giữa các listing.

## Lưu ý

- Script lưu danh sách sản phẩm hiện có vào `data/state/` để lần sau so sánh. Đừng xoá thư mục `data/`.
- Phần so sánh nghĩa là "mới kể từ lần chạy trước". Nên chạy **mỗi ngày một lần vào cùng một giờ**, ví dụ 23:30 giờ UK hoặc sáng hôm sau với `--date` là ngày hôm trước. Nếu nghỉ vài ngày, lần chạy kế tiếp sẽ gom hết listing của những ngày đó (cột `published_at` để trống với các dòng `diff`).
- Chỉ thấy được sản phẩm đã **publish**. Draft và private không hiện trên các nguồn công khai.
- Nếu site báo `KHONG KIEM TRA DUOC`: site đang chặn (Cloudflare), tắt feed hoặc Store API. Xem dòng `(!)` để biết lỗi cụ thể.
- Chỉnh danh sách site hoặc số trang tối đa trong `config.json`.

## Chạy tự động (Claude routine)

Routine chạy mỗi ngày lúc 23:24 giờ UK trên cloud. Mỗi lần chạy, kết quả (`reports/`) và danh sách so sánh (`data/state/`) được commit lên branch `claude/gifted-tesla-l4ekcx`, nên lần sau luôn có dữ liệu để so sánh.

Lưu ý: RFS và CFS đã tắt RSS feed, nhưng không ảnh hưởng vì nguồn chính là WP REST.

## Chạy tự động mỗi ngày (Windows)

Mở Task Scheduler → Create Basic Task → Daily → Action: *Start a program*:
- Program: `python`
- Arguments: `check_new_listings.py`
- Start in: đường dẫn tới thư mục `listing-monitor`

## Test

```
python -m unittest discover -s tests
```
