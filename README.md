# opencode-config-editor

[English Version](./README_EN.md) | **Tiếng Việt**

Trình chỉnh sửa đồ họa (GUI) cho các file cấu hình của [opencode](https://opencode.ai) —
`opencode.json` và `tui.json`. Ứng dụng giúp chỉnh sửa cấu hình một cách trực quan, thay vì
phải sửa JSON thủ công, với hỗ trợ xác thực theo schema, import/export và nhiều tiện ích khác.

![Version](https://img.shields.io/badge/version-4.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![GUI](https://img.shields.io/badge/GUI-PySide6-green)

## Tính năng

- **Chỉnh sửa trực quan** cho các file `opencode.json` (global + theo project) và `tui.json`.
- **10 tab chuyên biệt**: General, Runtime, Agents, Commands, Providers, MCP Servers, Plugins, Permissions, TUI, Raw JSON.
- **Quản lý model nâng cao**: thêm/sửa/xóa model, chỉnh sửa hàng loạt (bulk edit), catalog model với preview và lọc.
- **Import/Export** provider, MCP server và plugin, kèm giải quyết xung đột.
- **Xác thực schema** với báo cáo lỗi chi tiết (dùng `jsonschema` nếu có, kèm kiểm tra cơ bản).
- **Undo/redo** cho mọi thao tác (giới hạn 100 bước).
- **Tìm kiếm/lọc** trên tất cả các tab.
- **Bật/tắt hàng loạt** cho plugin và MCP server.
- **Sao lưu (backup)** tự động trước khi ghi file và chức năng Export.
- **Giao diện**: theme sáng/tối (theo hệ thống), điều chỉnh cỡ chữ, phím tắt thông dụng.
- **Raw JSON tab** với syntax highlighting và xác thực trực tiếp (debounced).

## Yêu cầu hệ thống

- Python 3.8+
- [PySide6](https://pypi.org/project/PySide6/) (bắt buộc)
- `jsonschema` (tùy chọn — dùng để xác thực schema đầy đủ)

## Cài đặt

### Cách 1: Cài đặt hệ thống (khuyến nghị)

```bash
# 1. Build file duy nhất từ các module trong src/
python3 build.py

# 2. Cài đặt (cần quyền root)
sudo bash install.sh
```

Sau khi cài đặt, chạy bằng lệnh:

```bash
opencode-editor
```

hoặc tìm "OpenCode Config Editor" trong menu ứng dụng (file `.desktop` được tạo tự động).

### Cách 2: Chạy trực tiếp (không cài đặt)

```bash
pip install PySide6
python3 build.py
python3 opencode-config-editor.py
```

## Cách sử dụng

1. Mở ứng dụng. Thanh công cụ có bộ chọn **Mode**:
   - **Global** — chỉnh sửa `~/.config/opencode/opencode.json` và `tui.json`.
   - **Local project…** — chọn một thư mục project để chỉnh sửa file `.opencode/opencode.json` và `.opencode/tui.json`.
2. Chỉnh sửa ở các tab tương ứng. Thay đổi được đánh dấu "dirty" và có thể lưu bằng `Ctrl+S`.
3. Dùng **Raw JSON** để sửa trực tiếp các key chưa có giao diện riêng.
4. Lưu, Export, hoặc Reload qua menu **File**.

### Phím tắt

| Thao tác | Phím |
| --- | --- |
| Mở file | `Ctrl+O` |
| Lưu | `Ctrl+S` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |
| Cắt / Sao chép / Dán | `Ctrl+X` / `Ctrl+C` / `Ctrl+V` |
| Toggle theme | `Ctrl+T` |
| Tăng / giảm cỡ chữ | `Ctrl++` / `Ctrl+-` |

## Cấu trúc dự án

```
.
├── src/                      # Mã nguồn dạng module
│   ├── 00_header.py          # Import, hằng số, cấu hình key
│   ├── 01_core.py            # Settings, theme, undo, validator, model catalog…
│   ├── 02_widgets.py         # Widget/dialog dùng chung
│   ├── 03_tabs.py            # 10 tab chỉnh sửa
│   ├── 04_main_window.py     # Cửa sổ chính (menu, toolbar, logic save/load)
│   └── 05_main.py            # Điểm vào (entrypoint)
├── build.py                  # Ghép các module src/ thành một file duy nhất
├── install.sh                # Script cài đặt hệ thống
├── opencode-config-editor.py # File đã build (đầu ra của build.py)
└── .archives/                # Các phiên bản cũ (v1 → v4)
```

## Build

```bash
python3 build.py
```

Script `build.py` ghép các file trong `src/` theo thứ tự khai báo trong `ORDER`
thành một file `opencode-config-editor.py` duy nhất, thuận tiện để phân phối và chạy.

## Xác thực schema

Ứng dụng lấy schema từ `https://opencode.ai/config.json` và `https://opencode.ai/tui.json`
(cache trong `~/.cache/opencode-config-editor/`). Nếu không cài `jsonschema`, ứng dụng sẽ
tự động chuyển sang bộ kiểm tra cơ bản dựa trên các key đã biết.

## Giấy phép

Xem [LICENSE](LICENSE).

---
**Tài liệu liên quan:**
- [Nhật ký thay đổi (Changelog)](CHANGELOG.md)
- [Hướng dẫn đóng góp (Contributing)](CONTRIBUTING.md)
