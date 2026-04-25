# AI Credit Management - Implementation Plan

Tài liệu này mô tả chi tiết các bước triển khai kỹ thuật (Implementation Plan) cho hệ thống Credit Management System tích hợp trong Kiro Gateway, dựa trên các yêu cầu nghiệp vụ từ BRD và cấu hình linh hoạt của hệ thống.

## 1. Kiến trúc Dữ liệu & Database Schema

Hệ thống cần phân tách rõ ràng giữa **Gateway Accounts** (dùng để log in vào cấu hình Dashboard) và **API Keys** (do người dùng cung cấp - BYOK).

- **Bảng `users` (Dashboard Accounts):**
  - `id`, `username`, `password_hash`, `role` (admin/user), `is_active`, `created_at`.
- **Bảng `kiro_user_mappings` (Import Mappings):**
  - `kiro_user_id` (được fetch từ `/getUsageLimits`), `email`, `username`, `imported_at`. Dùng để join khi hiển thị thông tin thay vì hiển thị ID thô.
- **Bảng `api_keys` (External Keys):**
  - `id`, `user_id` (owner), `kiro_user_id` (để map với bảng mappings), `key_hash` (hoặc encrypted key), `key_prefix`, `key_suffix` (để mask trên UI, e.g., `sk-proj...8f92`), `is_active`, `created_at` (Lưu ý: Mặc định tất cả các key đang active đều pool vào shared list nếu tính năng Usage Sharing được bật ở cấp global).
- **Bảng `key_usage` (Telemetry/Quota):**
  - `key_id`, `month` (e.g., `2026-04`), `current_usage` (cache count), `usage_limit` (sync từ Kiro API `/getUsageLimits`), `last_used_at`.

---

## 2. Chi tiết Triển khai: Global Model Enforcement (Override)

**Mục tiêu:** Cấu hình động việc bắt buộc (enforce) toàn bộ request đi qua Gateway sử dụng một model nhất định (ví dụ mặc định là `auto` hoặc do admin chọn trên UI) thay vì dựa vào model mà client báo lên. Tính năng này kế thừa và mở rộng cơ chế default auto model hiện tại thành luồng điều khiển config-driven.

**Implementation Task:**
1. **Config parameters:**
   - Bổ sung cấu hình (có thể lưu DB hoặc ENV): `ENFORCED_GLOBAL_MODEL` (ví dụ: `auto`, `claude-haiku-4.5`).
   - Thêm cờ bật/tắt tính năng ghi đè: `ENABLE_MODEL_OVERRIDE=true/false`.
2. **Gateway Interceptor (`converters_*.py`):**
   - Trước khi build Kiro Payload (tại `build_kiro_payload` và `build_kiro_payload_anthropic`).
   - Kiểm tra logic: `if ENABLE_MODEL_OVERRIDE and ENFORCED_GLOBAL_MODEL is not None`.
   - Nếu thỏa mãn, trích xuất request và ghi đè: `request.model = ENFORCED_GLOBAL_MODEL`.
   - Ghi Log thao tác (Level INFO) ví dụ: `Overriding user model {old_model} to enforced global model {ENFORCED_GLOBAL_MODEL}`.
3. **Model Validation (`model_resolver.py`):**
   - Đảm bảo model ghi đè hợp lệ và pass bypass qua cơ chế kiểm tra `is_known_model`.

---

## 3. Chi tiết Triển khai: Usage Sharing (Fallback Routing)

**Mục tiêu:** Gateway không tự ý block tính quota offline để bảo đảm trải nghiệm mà sẽ đóng vai trò smart-router. Thay vào đó, khi số Remaining Usage (Limit - Current Usage) của một Key tụt xuống dưới 1% so với Limit, request tự động định tuyến sang dùng Key khác trong hệ thống. Luồng check này chỉ nhằm mục đích routing trước khi đẩy request đi. Việc cập nhật (tracking usage) chỉ thực hiện bất đồng bộ sau khi user request đã hoàn thành xong.

**Implementation Task:**
1. **Quản lý Cấu hình và Cache (Redis/Shared Memory):**
   - **Caching Cấu hình:** Chức năng Usage Sharing cần được bật/tắt qua config (cache in-memory hoặc Redis, cập nhật reload ngay khi có biến động từ Admin/DB).
   - **Caching Usage:** Lưu trạng thái Limit và Current Usage của toàn bộ API Keys để tính toán siêu tốc (O(1) lookup). Phải thiết kế safe-concurrency (như dùng Redis) để hỗ trợ chạy **multi-process** (như Uvicorn/Gunicorn workers) đảm bảo phục vụ được nhiều request đồng thời, không gây race condition.
2. **Điều kiện Fallback Mechanism:** Kích hoạt luồng routing tự động nếu:
   - **Pre-check:** Gateway lấy thông tin usage từ cache. Nếu `(cache_usage_limit - cached_current_usage) / cache_usage_limit < 0.01` (Remaining Usage dưới 1%), lập tức đổi Key lúc bắt đầu nhận Request.
   - **Post-check:** Call Kiro API backend trả về lỗi liên quan đến Quota Limit (`429 Too Many Requests`).
3. **Thuật toán Fallback (Round-Robin trong Pool Toàn cục):**
   - Không cần dùng cờ `is_shared`. Mặc định nếu bật Usage Sharing, query danh sách **toàn bộ** các Active Key từ DB/Cache.
   - Lọc các Active Key có Remaining Usage > 1% (có thể bù safety margin nhỏ).
   - Trích xuất 1 Key bằng Round-Robin và cập nhật Auth header.
4. **Retry Logic Gateway (`http_client.py`):**
   - Chèn logic vào `httpx.AsyncClient`: Bắt exception 429 do cạn Quota.
   - Gọi hàm map sang key mới $\rightarrow$ Trigger Retry Request (không gửi thông báo lỗi này ngược lại cho thiết bị của Client).

---

## 4. Chi tiết Triển khai: Telemetry Tracking & API References (SLA 1 phút/Multi-process)

**Mục tiêu:** Cập nhật Dashboard Usage chỉ xảy ra sau khi Request hoàn tất (bất đồng bộ) để hỗ trợ Multi-process/Multi-thread mà không block người dùng. Đồng thời, liên kết tới API Contract từ tài liệu references.

**Implementation Task:**
1. **Background Tracking (Non-blocking):**
   - Viết một `BackgroundTasks` hoặc trigger vào luồng `Stream Parser` sau khi Response đã flush chunk data cuối cùng. Tính năng này đóng việc Increment atomic counter cho hệ thống cache (Redis HINCRBY để bảo vệ tính toàn vẹn khi Multi-Process).
   - Tuyệt đối không query RDBMS (SQL) tại vòng lặp request nhằm giúp các Worker phân luồng liên tục.
2. **Sync Worker (Cron-task):**
   - Một Process / Master node riêng biệt chạy loop định kỳ mỗi phút thu thập usage counter từ Redis và persist log lên RDBMS `key_usage`. Nếu dùng Multi-workers (Uvicorn), cần khoá leader-election hoặc giao cho worker đầu tiên để tránh duplicate DB calls.
3. **Đồng bộ Limits Định kỳ (Fetcing):**
   - Cung cấp Background Job: **Định kỳ (VD: mỗi 5-15 phút)** call API `/getUsageLimits` trên tập các Key có biến động, refresh lại cấu hình cache. Lưu ý reference các file sau để implement chính xác:
     - [getUsageLimits.md](../getUsageLimits.md) - Contract API Limit để đồng bộ `usageLimit` và `currentUsage`.
     - [getAssistanceResponse.md](../getAssistanceResponse.md) - Contract API chat completion tạo token data cần theo dõi.
     - [getListModels.md](../getListModels.md) - Contract sử dụng Global Override.

---

## 5. Chi tiết Triển khai: Import Mapping Users (Kiro UserID to Email/Username)

**Mục tiêu:** API Key khi gọi lên `/getUsageLimits` chỉ trả về `userId` (ví dụ: `identity-id` hoặc định danh AWS thô). Do đó, Dashboard phải có khả năng import danh sách users mapping ID này ra định danh con người dễ đọc (như `email` hoặc `username`) phục vụ mục đích báo cáo.

**Implementation Task:**
1. **Tính năng Upload Import (API/CLI):**
   - Viết API / Batch process cho admin upload danh sách user (định dạng CSV/JSON) chứa ít nhất 3 cột: `userId` gốc, `email`, `username`.
   - Dữ liệu này được upsert (insert hoặc update) vào bảng `kiro_user_mappings`.
2. **Quá trình Mapping tự động:**
   - Background Job gọi `getUsageLimits`: Gateway trích xuất `userId` nằm trong response của Kiro.
   - Cập nhật trường `kiro_user_id` trong bảng `api_keys` để liên kết vĩnh viễn khóa này với người dùng trên Kiro.
3. **Truy vấn Hiển thị (Telemetry view):**
   - Bất kỳ API trả dữ liệu hiển thị nào cho Gateway Dashboard (như Get Quotas, Report Daily/Monthly) đều phải JOIN dữ liệu qua bảng `kiro_user_mappings` để thay thế thông tin ID thô thành Email và Username để phục vụ hiển thị tường minh.

---

## 6. Verification & Acceptance Criteria (AC)

- [ ] **AC 1 (Model Override):** Bật `ENABLE_MODEL_OVERRIDE` và cấu hình `ENFORCED_GLOBAL_MODEL="auto"`. Gateway ghi đè model người dùng trước khi gửi luồng gọi Kiro, không làm ảnh hưởng đến payload body khác.
- [ ] **AC 2 (Fallback - Cached Limits < 1%):** Key A của user đã push tracking counter chạm mốc **> 99% Limit** ban đầu (Còn dưới 1%). Request mới vào sẽ route bằng Key C trong nhóm chung (tất cả các key đang Active). Phân tải chạy an toàn kể cả khi có 10 concurrent requests vào cùng hệ thống 4 Workers process.
- [ ] **AC 3 (Fallback - Backend 429 Reject):** Kiro trả về 429 Quota Exhausted với Key đang dùng. Kích hoạt Retry Logic sang Key có tỉ lệ dư trên 1% và trả stream thành công.
- [ ] **AC 4 (Telemetry Performance):** Toàn bộ Logic Tracking là bất đồng bộ (trả request xong mới tính tiền). Đảm bảo Latency P99 của Request tới lúc nhận Data First Chunk luôn được duy trì mượt mà dù đang hit quota check.
- [ ] **AC 5 (User mapping Import):** Upload file CSV để push file user list vào hệ thống. Sau khi hệ thống đồng bộ API lấy `getUsageLimits` và update DB, request lấy history/metric trả về đúng `email` người sở hữu key thay vì ID AWS/Kiro string.