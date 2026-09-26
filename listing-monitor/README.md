# Listing Monitor: kiểm tra listing mới mỗi ngày

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
