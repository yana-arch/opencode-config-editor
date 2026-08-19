# Changelog

[English Version](./CHANGELOG_EN.md) | **Tiếng Việt**

---
[← Quay lại README](README.md)

Tất cả các thay đổi đáng chú ý của dự án được ghi lại trong file này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/),
và dự án tuân theo [Semantic Versioning](https://semver.org/lang/vi/).

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
