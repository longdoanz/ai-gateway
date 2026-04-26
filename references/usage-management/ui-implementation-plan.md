# UI Implementation Plan - AI Credit Management Dashboard

Tài liệu này mô tả chi tiết kế hoạch triển khai Frontend (UI) cho hệ thống Credit Management System dựa trên **Next.js** và **Tailwind CSS**, tuân thủ nghiêm ngặt các nguyên tắc từ BRD (Minimalism Glassmorphism Light).

## 1. Tech Stack Overview
- **Core Framework:** **Next.js** (Sử dụng App Router `app/` directory cho layout lồng nhau và routing hiện đại).
- **Styling:** **Tailwind CSS** (Utility-first CSS, cực kỳ phù hợp để tạo các class Glassmorphism và quản lý màu sắc theo System Design).
- **UI Components:** **Shadcn UI** (Cung cấp các component unstyled nhưng accessible như Tabs, Table, Dialog, Switch. Hoàn hảo để build Data Table có row-expansion).
- **Data Fetching & State:** **TanStack Query (React Query)** (Quản lý server state, polling data mỗi 1 phút theo SLA, caching dữ liệu usage dashboard).
- **Data Visualization (Charts):** **Tremor** hoặc **Recharts** (Vẽ các biểu đồ đường 30-ngày, bar chart tiêu thụ tài nguyên).
- **Icons:** **Lucide React**.

---

## 2. Design System Token (Tailwind Config - Glacier Light System)

Cấu hình `tailwind.config.js` cần bám sát dải màu và font chữ đã chốt:

- **Background Palette:**
  - Nền chính ứng dụng: `#F8FAFC` (Slate 50).
- **Glassmorphism Surfaces (Card/Modal/Panel):**
  - Mức cơ bản: `bg-white/70 backdrop-blur-2xl border border-slate-200/80`.
- **Accent Colors:**
  - Primary (Chính): Sky Blue `#0EA5E9` (Cyan/Sky tùy chỉnh).
  - Secondary (Nhấn/Chart): Indigo `#6366F1`.
- **Typography:**
  - Font Text/Heading: **Inter** (cài đặt qua `next/font/google`).
  - Font Data/Keys/Numbers: **JetBrains Mono** (Dùng cho thông tin Masked Key, số liệu Credit).

---

## 3. Kiến trúc Thư mục (Directory Structure)

```text
webui/
├── app/
│   ├── (auth)/
│   │   └── login/page.tsx               # Màn hình đăng nhập Gateway Account
│   ├── (dashboard)/
│   │   ├── layout.tsx                   # Layout chứa Sidebar navigation và Topbar
│   │   ├── page.tsx                     # Screen 1: Monthly Overview Dashboard
  │   │   ├── users/
  │   │   │   └── page.tsx                 # Screen 2: User & API Key Management Hub
  │   │   ├── import/
  │   │   │   └── page.tsx                 # Screen 3: User Mapping Import
  │   │   ├── accounts/
  │   │   │   └── page.tsx                 # Screen 4: Account Management
  │   │   └── settings/
  │   │       └── page.tsx                 # Screen 5: Gateway Configuration
│   ├── globals.css                      # Global styles & Tailwind directives
│   └── layout.tsx                       # Root layout (Provider bọc React Query)
├── components/
│   ├── ui/                              # Chứa các component từ Shadcn UI (button, table, tabs...)
│   ├── charts/                          # Reusable components cho biểu đồ usage
│   └── layout/                          # Sidebar, Header
├── lib/
│   ├── api.ts                           # Axios instance cấu hình intercept JWT
│   └── utils.ts                         # Helper functions (maskKey, formatCredit...)
└── hooks/
    └── useUsageData.ts                  # React Query hooks (polling usage)
```

---

## 4. Chi tiết Triển khai các Màn hình (Screens)

### Screen 1: Monthly Overview Dashboard (`app/(dashboard)/page.tsx`)
- **Bố cục (Bento Grid Layout):** Sử dụng CSS Grid (`grid-cols-1 md:grid-cols-3 lg:grid-cols-4`).
- **KPI Cards (Glassmorphism):**
  - Total Credits Burned (Highlight bằng font JetBrains Mono).
  - User Growth / Active Keys.
  - Remaining Budget.
- **Main Chart:** Biểu đồ "30-day consumption trend" (Sử dụng AreaChart của Tremor/Recharts với mã màu mix độ trong suốt `#0EA5E9` sang transparent).
- **Constraint:** Tuyệt đối **không** render nút "Buy Credits" hay các module nạp tiền.

### Screen 2: User & API Key Management Hub (`app/(dashboard)/users/page.tsx`)
Đây là màn hình cốt lõi có tương tác sâu. Sử dụng `Tabs` component của Shadcn. Quyền `user` chỉ thấy data của chính mình, quyền `admin` thấy toàn bộ theo backend API.

**Tab 1: Access & Overrides (Data Table)**
- **TanStack Table Implementation:**
  - Danh sách Key theo chủ sở hữu (Owner).
  - Cấu hình tính năng **Row Expansion**: Khi click vào một hàng (Owner), sổ xuống table con hiển thị chi tiết các khóa API (External Keys) đang map.
- **Key Display:** Format chuỗi mã hóa `sk-proj-ax...8f92` (Class font `font-mono text-sm`).
- **Toggles:** Nút Switch (Shadcn) bật/tắt (Active/Inactive) fallback status ngay trên từng row. Call mutation API ngay khi toggle bằng React Query.
- **Modal Add/Override:** Dialog thêm API key, chỉ gán Key, không hiển thị lại Full key sau khi thêm.

**Tab 2: Usage Analytics**
- Hiển thị các BarChart (biểu đồ cột) so sánh user burn rate.
- Lọc theo ngày/tháng.

### Screen 3: User Mapping Import (`app/(dashboard)/import/page.tsx`)
- **Mục đích:** Map `kiro_user_id` (ví dụ AWS identity) thành `username` hoặc `email` để báo cáo có ý nghĩa.
- **Tính năng Upload:** Vùng Kéo-thả (Drag & Drop zone) xử lý file CSV/JSON.
- **Cấu trúc Dữ liệu Yêu cầu:** `kiro_user_id` (Bắt buộc), `email`, `username`.
- **Preview & Confirm:** Bảng Data Table preview hiển thị các dòng hợp lệ/lỗi trước khi nhấn nút "Import to Database".

### Screen 4: Account Management (`app/(dashboard)/accounts/page.tsx`)
- **Quyền hạn (Role-based):** Màn hình này giới hạn theo role trong JWT, ưu tiên luồng `admin` để quản trị tài khoản Dashboard.
- **Danh sách Tài khoản (Bảng `users`):** Hiển thị các tài khoản của hệ thống quản lý (Dashboard Accounts).
- **Thao tác CRUD:** Thêm mới (Create), Khóa (Deactivate - toggle `is_active`), Đổi mật khẩu (Reset password) và Phân quyền (`admin` hoặc `user`).

### Screen 5: Gateway Configuration (`app/(dashboard)/settings/page.tsx`)
- **Mục đích:** Cấu hình động các thông số của Gateway (bảng `system_config` trong backend). Dùng Shadcn Form + React Hook Form.
- **Cấu hình Global Model Enforcement (Ghi đè model):**
  - Switch: Bật/Tắt `enable_model_override`.
  - Select/Input Box: Chọn model bắt buộc (ví dụ `auto`, `claude-haiku-4.5`).
- **Cấu hình Usage Sharing (Fallback):**
  - Switch: Bật/Tắt `enable_usage_sharing`. Kích hoạt cơ chế round-robin tự động mượn key dự phòng khi key chính còn dưới 1% limit.
- **Save & Reload Cache:** Nút Apply sẽ gọi API `PUT /api/config` để backend lập tức update state in-memory router mà không cần restart server.

---

## 5. Tích hợp Dữ liệu & Xử lý Trạng thái (SLA 1 Phút)

**API Endpoint Contract (chuẩn hóa theo backend hiện tại):**
1. **Authentication:**
  - `POST /api/auth/login` -> nhận `access_token` + `refresh_token`.
  - `POST /api/auth/refresh` -> cấp mới token khi access token hết hạn.
2. **Overview Dashboard:**
  - `GET /api/overview` -> KPI tổng quan + daily usage 30 ngày.
3. **User Management:**
  - `GET /api/users`, `POST /api/users`, `GET /api/users/{id}`, `PUT /api/users/{id}`.
4. **API Key Management:**
  - `GET /api/keys`, `POST /api/keys`, `PUT /api/keys/{id}`, `DELETE /api/keys/{id}`, `GET /api/keys/{id}/usage`.
5. **System Configuration:**
  - `GET /api/config`, `PUT /api/config`.
6. **Import Mapping Users:**
  - `POST /api/import/users` (multipart/form-data, hỗ trợ CSV/JSON).

**Role-based Authorization (giai đoạn hiện tại):**
1. Chỉ áp dụng mức role trong JWT, chưa triển khai ma trận RBAC chi tiết theo action.
2. JWT payload tối thiểu gồm: `sub`, `role`, `exp`.
3. Frontend đọc claim `role` để điều hướng hiển thị menu và bảo vệ route cấp trang:
  - `admin`: truy cập đầy đủ các màn hình Dashboard, Accounts, Settings, Import.
  - `user`: truy cập màn hình Overview và khu vực thao tác key của chính mình (theo response filtering từ backend).

**Data Fetching & Polling:**
1. Để đạt SLA hiển thị dữ liệu trễ dưới 1 phút: cấu hình TanStack Query với `refetchInterval: 60000`.
2. Mẫu hook:
  ```typescript
  export const useDashboardMetrics = () => {
    return useQuery({
     queryKey: ['usage', 'overview'],
     queryFn: fetchUsageOverview,
     refetchInterval: 60000,
     staleTime: 30000,
    });
  };
  ```

---

## 6. Các Phase Triển khai Đề xuất

- **Phase 1: Setup & Design System (2 ngày)**
  - Init Next.js, cài đặt Tailwind, font Inter & JetBrains Mono.
  - Import Shadcn UI base components, setup theme màu Glacier Light.
- **Phase 2: Layout & Auth (2 ngày)**
  - Dựng layout Sidebar, màn hình Login kết nối với API backend có sẵn.
- **Phase 3: Screen - Monthly Dashboard (3 ngày)**
  - Dummy data. Tích hợp Tremor/Recharts.
  - Thay thế data thật qua API fetching.
- **Phase 4: Screen - User & Key Management (5 ngày)**
  - Xây dựng Data Table với tính năng bung hàng (row expansion) phức tạp.
  - Tích hợp CRUD (Thêm, Xóa, Bật/tắt) các Keys và Mappings.
- **Phase 5: Import, Accounts & Settings (4 ngày)**
  - Màn hình Import (CSV Drag/Drop mapping UserId -> Email).
  - Role-based JWT: Phân quyền admin/user ở cấp route màn hình.
  - Gateway Setup (Thao tác với bảng `system_config` của FastAPI).
- **Phase 6: Refine & Optimization (2 ngày)**
  - Kiểm tra các hiệu ứng Glassmorphism.
  - Tuning performance cho TanStack Query (Polling cache xử lý rác).