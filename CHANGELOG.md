# Changelog

[English Version](./CHANGELOG_EN.md) | **Tiếng Việt**

---
[← Quay lại README](README.md)

Tất cả các thay đổi đáng chú ý của dự án được ghi lại trong file này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/),
và dự án tuân theo [Semantic Versioning](https://semver.org/lang/vi/).

## [4.3.1] - 2026-08-20

### Changed

- Tách module lớn thành 21 file nhỏ theo miền (settings, config, parsing, catalog,
  provider fetch, widgets common/models/catalog, 10 tab riêng, main window, main).
  Không đổi hành vi — code được chuyển nguyên vẹn, build ghép như cũ, 75 tests PASS.

## [4.3.0] - 2026-08-20

Tối ưu duyệt match hàng loạt + **Reference provider fallback** cho model không match.

### Added

- **Reference provider** trong Fetch from API: chọn provider tham chiếu làm nguồn
  fallback cho các model không tìm thấy trong catalog.
- **Fallback 4 cấp**: exact trong provider tham chiếu → normalized id (strip
  suffix version/ngày kiểu `-2024-08-13`, `-v2`, `-latest`) trong provider tham chiếu →
  normalized toàn catalog → prefix chung dài nhất trong provider tham chiếu.
- Dòng fallback hiển thị status `fallback:<provider>` (màu xanh), chỉ fill-missing.
- **Map… thủ công**: dòng `unknown` có nút mở Catalog Model Picker (tìm kiếm được)
  để map sang model catalog bất kỳ, status `mapped` (màu tím).
- **Persist mapping** `unknown → catalog id` vào QSettings; lần fetch sau tự nhớ.
- Checkbox **"Apply fallback"** bật/tắt hàng loạt dòng fallback.

### Changed

- Match sau fetch và trong Models Manager giờ gộp về **một dialog duyệt duy nhất**
  (trước đây model ambiguous phải confirm từng cái).
- Combo provider mặc định chọn theo xếp hạng: provider trùng tên trước, rồi
  provider có dữ liệu đầy đủ nhất (`_sort_matches`); dòng ambiguous được pre-check.

## [4.2.0] - 2026-08-20

Tính năng **Fetch Models từ API provider**: nhập provider mới bằng cách fetch danh sách model trực tiếp từ API.

### Added

- Nút **"Fetch from API"** trong tab Providers: nhập provider key + Base URL + API key,
  chọn định dạng API rồi fetch danh sách model.
- Hỗ trợ 5 định dạng API: **OpenAI-compatible** (`/models`), **Anthropic/Claude**
  (`/v1/models`), **Google Gemini** (`/v1beta/models`), **models.dev** (api.json),
  và **Generic JSON** (tự khai báo đường dẫn mảng model + field id/name).
- Fetch chạy trong **QThread** không block UI; danh sách model hiện kèm checkbox chọn.
- **Auto-match sau fetch**: model fetch về (chỉ có id/name) được tự động match với catalog
  models.dev để điền context/output/cost/modalities; model trùng nhiều provider sẽ hỏi chọn.
- Bảo mật: chặn SSRF tới localhost/IP nội bộ (trừ khi bật "Allow local URL"),
  API key chỉ gửi qua header và không lưu vào config, timeout request.

## [4.1.0] - 2026-08-20

Tính năng **Model Format Match & Apply**: chuẩn hóa và match model từ catalog models.dev.

### Added

- **Browse Model Catalog**: duyệt toàn bộ catalog (190+ provider, 6800+ model) với bộ lọc
  context/output tier, modality, capability; xem chi tiết format chuẩn hóa; export CSV/JSON.
- **Match & Format Models from Catalog**: match từng model id trong config với catalog,
  tìm provider chứa nó, tự điền format chuẩn hóa (context, output, modalities, cost,
  capability flags) theo chế độ fill-thiếu hoặc ghi đè.
- **Match theo từng model / cả provider** ngay trong Models Manager (nút "Match" mỗi dòng
  và "Match from Catalog").
- **Preview diff trực quan old → new** trước khi áp: từng field với màu thêm/sửa/xóa,
  chọn provider cho model trùng nhiều provider bằng dropdown, checkbox overwrite.
- **Catalog tier settings** cấu hình ngưỡng context/output để lọc.
- Bundle catalog models.dev (`models/models.dev.catalog.json`) tự nạp khi mở dialog.
- **Test suite** (`tests/`, 32 tests) cho core matching/normalization + index tìm model
  nhanh; tích hợp vào `build.py` và CI.

## [4.0.0] - 2026-08-19

Phiên bản viết lại lớn, chuyển từ file đơn sang kiến trúc module + build system.

### Added

- Kiến trúc module trong `src/` (00_header → 05_main) và script build `build.py`
  ghép thành một file duy nhất.
- 10 tab chỉnh sửa: General, Runtime, Agents, Commands, Providers, MCP Servers,
  Plugins, Permissions, TUI, Raw JSON.
- Quản lý model nâng cao: bulk edit, catalog model với preview và lọc.
- Import/Export provider, MCP server và plugin kèm giải quyết xung đột.
- Xác thực schema (`jsonschema`) với báo cáo lỗi chi tiết và bộ kiểm tra cơ bản dự phòng.
- Undo/redo cho mọi thao tác (giới hạn 100 bước).
- Tìm kiếm/lọc trên tất cả các tab; bật/tắt hàng loạt plugin và MCP server.
- Theme sáng/tối theo hệ thống; điều chỉnh cỡ chữ; phím tắt thông dụng.
- Sao lưu tự động trước khi ghi file; chức năng Export.
- Raw JSON tab với syntax highlighting và xác thực trực tiếp (debounced).
- Script cài đặt `install.sh` (tạo lệnh `opencode-editor` và shortcut `.desktop`).

### Changed

- Toàn bộ code được tổ chức lại theo module thay vì một file lớn duy nhất.

## [3.0.0] - trước 2026-08-19

Phiên bản trung gian (lưu trữ trong `.archives/opencode-config-editor.v3.py`).

## [2.0.0] - trước 2026-08-19

Phiên bản trung gian (lưu trữ trong `.archives/opencode-config-editor.v2a.py`).

## [1.0.0] - trước 2026-08-19

Phiên bản đầu tiên (lưu trữ trong `.archives/opencode-config-editor.v1a.py`
và `.archives/opencode-config-editor.v1b.py`).

> **Ghi chú**: Ngày phát hành chính xác của các phiên bản 1.x–3.x không được ghi lại
> trong lịch sử git (chỉ có một commit cho v4.0.0). Các mục trên được tổng hợp từ
> các file lưu trữ trong `.archives/` và có thể chưa chính xác tuyệt đối.
