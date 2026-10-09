# Hướng dẫn chạy Listing Monitor trên máy tính của bạn

Tool chạy hoàn toàn trên máy bạn. Key API (nếu có) chỉ nằm trong file `.env` trên máy và không bao giờ được đưa lên GitHub.

Mỗi lần chạy, tool check **ngày UK vừa kết thúc** (chạy buổi sáng giờ Việt Nam là đủ cả ngày bên UK), rồi tự mở file Excel lỗi.

---

## 1. Cài đặt (làm 1 lần)

1. **Python 3.9 trở lên**: tải ở https://www.python.org/downloads/
   - Windows: khi cài nhớ tick **Add Python to PATH**.
2. **Tải tool về máy**, chọn 1 trong 2 cách:
   - **GitHub Desktop** (khuyên dùng, sau này cập nhật tool chỉ cần 1 click): File → Clone repository → `thuytran278/work`, rồi đổi sang branch `claude/gifted-tesla-l4ekcx`.
   - **Tải ZIP**: vào https://github.com/thuytran278/work/tree/claude/gifted-tesla-l4ekcx → Code → Download ZIP, rồi giải nén.
3. **Cài thư viện**: mở thư mục `listing-monitor`, gõ `cmd` vào thanh địa chỉ (Windows) hoặc mở Terminal tại thư mục đó (Mac), rồi chạy:
   ```
   pip install -r requirements.txt
   ```
   (Mac dùng `pip3` nếu `pip` báo lỗi.)

## 2. Chạy

- **Windows**: bấm đúp chuột vào `run_daily.bat`.
- **Mac**: mở Terminal tại thư mục `listing-monitor`, rồi chạy `sh run_daily.sh`.

Chạy xong, file Excel tự mở. Mọi kết quả nằm trong `reports/<ngày>/`:
- `new_listings_<ngày>.csv`: danh sách listing mới.
- `summary.txt`: tóm tắt listing mới.
- `qa_<ngày>.xlsx`: lỗi của từng listing, mỗi web 1 sheet.
- `qa_summary.txt`: tóm tắt lỗi.

Muốn chạy cho một ngày khác:
```
python check_new_listings.py --date 2026-10-08
python qa_listings.py --date 2026-10-08 --open
```

## 3. Đặt lịch tự chạy mỗi sáng

Máy phải đang bật vào giờ chạy. Nếu máy tắt thì lần sau bấm chạy tay là được.

**Windows (Task Scheduler)**
1. Mở Start, gõ **Task Scheduler**, chọn **Create Basic Task**.
2. Name: `Listing Monitor`. Trigger: **Daily**, lúc **7:00 sáng**.
3. Action: **Start a program**.
   - Program: chọn file `run_daily.bat`
   - Add arguments: `auto` (để cửa sổ tự đóng khi chạy xong)
   - Start in: đường dẫn thư mục `listing-monitor`, ví dụ `C:\Users\Clara\work\listing-monitor`
4. Finish. Sau đó vào Properties của task, tick **Run task as soon as possible after a scheduled start is missed**.

**Mac**
1. Mở Terminal, gõ `crontab -e`.
2. Thêm dòng sau (sửa lại đường dẫn cho đúng máy bạn):
   ```
   0 7 * * * sh /Users/clara/work/listing-monitor/run_daily.sh
   ```

> Vì sao chọn 7:00 sáng giờ VN: lúc đó ngày bên UK đã kết thúc (UK chậm hơn VN 6 tiếng theo giờ mùa hè, 7 tiếng theo giờ mùa đông), nên tool check đủ listing của cả ngày hôm trước.

## 4. Thêm key API (không bắt buộc)

Chưa có key, tool vẫn chạy bằng dữ liệu công khai như từ trước tới giờ.

1. Copy file `.env.example` thành `.env` (cùng thư mục `listing-monitor`).
2. Mở `.env` bằng Notepad (Windows) hoặc TextEdit (Mac), điền key sau dấu `=` rồi lưu.
3. **Không gửi file `.env` cho ai, không dán key vào chat.** File này đã được chặn không cho lên GitHub, và Claude Code cũng được cấu hình không đọc nó (`.claude/settings.json`).

> Phần check bằng key (Draft/Pending, focus keyword Rank Math, variation, coupon Free Pin) sẽ được bổ sung khi bạn có key và đã chạy thử trên máy.

## 5. Tạo key an toàn (gửi người quản trị web)

Làm riêng trên từng web:
1. Cài plugin **User Role Editor**. Tạo role `QA Read Only` chỉ có các quyền:
   - `read`
   - `read_private_products`
   - `read_private_shop_coupons` (để tool check được coupon Free Pin)

   **Không** cấp quyền đơn hàng (`read_private_shop_orders`) hay bất kỳ quyền edit nào.
2. Tạo user mới, ví dụ `qa-bot`, gán role `QA Read Only`.
3. Đăng nhập bằng user `qa-bot`, vào WooCommerce → Settings → Advanced → REST API → **Add key**. Đặt Description là `Listing Monitor`, chọn User `qa-bot`, Permissions **Read**.
4. Copy Consumer key và Consumer secret vào file `.env` trên máy bạn.
5. Ở trang REST API sẽ có cột **Last access**. Thấy gì lạ thì bấm **Revoke** để key hết tác dụng ngay. Nên tạo key mới khoảng 3 tháng một lần.

## 6. Dùng cùng Claude Code trên máy (tuỳ chọn)

Tool tự chạy được mà không cần AI. Khi muốn AI đọc và giải thích kết quả, bắt thêm lỗi tool chưa có rule, hoặc sửa rule: mở thư mục `work` bằng Claude Code (bản desktop hoặc terminal) rồi nhắn như bình thường, ví dụ "chạy check lỗi hôm nay giúp mình".

## 7. Cập nhật tool khi có rule mới

- **GitHub Desktop**: bấm **Fetch origin**, rồi **Pull**.
- **Tải ZIP**: tải ZIP mới về rồi copy đè lên thư mục cũ, nhưng **không copy thư mục `data/`** (để giữ lịch sử theo dõi trên máy). File `.env` không có trong ZIP nên không bị mất.

Lịch sử theo dõi của bạn (`data/state/`) và báo cáo (`reports/`) nằm trên máy và không bị mất khi cập nhật.
