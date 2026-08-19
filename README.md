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

### Cách 1: Tự tải release từ GitHub (khuyến nghị)

`install.sh` tự tải release mới nhất từ GitHub về, di chuyển vào `/opt/opencode-editor/`,
tạo lệnh `opencode-editor` và shortcut trong menu ứng dụng:

```bash
curl -fsSL https://raw.githubusercontent.com/yana-arch/opencode-config-editor/master/install.sh | sudo bash
```

Hoặc tải script về rồi chạy ở chế độ **remote**:

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/yana-arch/opencode-config-editor/master/install.sh
sudo bash install.sh --remote
```

### Cách 2: Cài từ file local

Nếu đã có sẵn file `opencode-config-editor.py` (ví dụ build thủ công hoặc tải về riêng), cài
trực tiếp mà không cần tải lại:

```bash
python3 build.py
sudo bash install.sh --local opencode-config-editor.py
```

Sau khi cài đặt (dù remote hay local), chạy bằng lệnh:

```bash
opencode-editor
```

hoặc tìm "OpenCode Config Editor" trong menu ứng dụng.

**Tuỳ biến cài đặt:**

```bash
# Cài từ repo khác
REPO=<owner/repo> sudo bash install.sh --remote

# Cài phiên bản cụ thể (mặc định: mới nhất)
VERSION=4.0.1 sudo bash install.sh --remote

# Bỏ qua cài đặt phụ thuộc
NO_DEPS=1 sudo bash install.sh --remote
```

**Xem trợ giúp đầy đủ:** `bash install.sh --help`

### Cách 3: Build thủ công từ mã nguồn

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
├── install.sh                # Script tự tải release từ GitHub và cài đặt
├── .github/workflows/        # GitHub Actions: build + release tự động
├── opencode-config-editor.py # File đã build (đầu ra của build.py)
└── .archives/                # Các phiên bản cũ (v1 → v4)
```

## Build & Release (CI/CD)

GitHub Actions tự động build file và tạo **GitHub Release** khi bạn đẩy tag:

```bash
git tag v4.0.0
git push origin v4.0.0
```

- Workflow: `.github/workflows/build-release.yml`
- Chạy `python3 build.py`, đóng gói asset `opencode-config-editor-<version>.py`
  kèm `CHANGELOG.md` / `CHANGELOG_EN.md`.
- Cũng có thể kích hoạt thủ công từ tab **Actions** → *Build & Release* → *Run workflow*
  (lúc đó asset được đính kèm dạng artifact, không phải release).

> **Ghi chú**: Workflow dùng `github.repository` tự động nên không cần cấu hình thêm.
> Nguồn tải mặc định của `install.sh` là `yana-arch/opencode-config-editor`; nếu fork,
> đặt biến `REPO` khi chạy để trỏ tới repo của bạn.

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
