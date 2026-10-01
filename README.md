# Trình Chỉnh Sửa Cấu Hình OpenCode & OpenClaude

[![Release Version](https://img.shields.io/badge/version-4.4.1-blue?style=flat-square)](https://github.com/yana-arch/opencode-config-editor/releases)
[![Python Version](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![GUI Framework](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt-41CD52?style=flat-square&logo=qt&logoColor=white)](https://pypi.org/project/PySide6/)
[![Validation](https://img.shields.io/badge/Schema-JSONSchema%20Draft%207-orange?style=flat-square)](https://json-schema.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](./LICENSE)
[![Build & Release](https://img.shields.io/github/actions/workflow/status/yana-arch/opencode-config-editor/build-release.yml?style=flat-square&label=CI%2FCD)](https://github.com/yana-arch/opencode-config-editor/actions)

> **Bộ công cụ đồ họa (GUI) quản trị cấu hình chuyên nghiệp dành cho các AI Coding Agent ([OpenCode](https://opencode.ai) & [OpenClaude / Claude Code](https://openclaude.gitlawb.com)). Hỗ trợ phân giải đa tầng kế thừa, che giấu API key bảo mật zero-leak, ghi file an toàn (Atomic Write), và đồng bộ tự động danh mục Model từ API.**

---

[English Version](./README_EN.md) | **Tiếng Việt**

---

## 📌 Tổng Quan & Vấn Đề Giải Quyết

Việc quản lý file cấu hình cho các coding agent hiện đại thường gặp nhiều bất cập:
1. **Dễ Lỗi Cú Pháp**: Sửa file JSON lồng nhau thủ công dễ gây sai cú pháp, lệch schema và mất mát các key cấu hình chưa rõ.
2. **Xung Đột Đa Tầng**: Cấu hình phân cấp (Enterprise Policy → User → Project → Local overrides) gây khó khăn trong việc xác định giá trị thực tế đang áp dụng.
3. **Nguy Cơ Lộ Bí Mật**: API key, token và auth headers hiển thị dạng plain text dễ bị rò rỉ khi chia sẻ màn hình hoặc livestream.
4. **Lệch Thông Số Model**: Việc cập nhật thủ công ID model, context window, token output và endpoint giữa các nhà cung cấp LLM tốn nhiều thời gian.

**OpenCode Config Editor** giải quyết triệt để các vấn đề trên thông qua giao diện đồ họa PySide6 hiện đại, cơ chế xác thực schema hai chiều, che giấu secret bảo mật, tự động fetch model từ API và lưu trữ an toàn chống hỏng file.

---

## 🏗️ Kiến Trúc Luồng Hoạt Động

```mermaid
flowchart TD
    subgraph UI_Layer ["1. Tầng Giao Diện Người Dùng (PySide6)"]
        FormTabs[Các Tab Biểu Mẫu Chuyên Biệt<br/><i>Providers, Models, MCP, Hooks, Permissions...</i>]
        RawTab[Trình Soạn Thảo Raw JSON<br/><i>Kiểm Tra Lỗi Cú Pháp Tức Thì (Debounced)</i>]
        SecretMask[Thành Phần MaskedLineEdit<br/><i>Mã Hóa & Ẩn API Key / Token</i>]
        InheritHint[Gợi Ý Giá Trị Kế Thừa Đa Tầng<br/><i>Hiển Thị Rõ Nguồn Gốc Cấu Hình</i>]
    end

    subgraph Core_Engine ["2. Bộ Xử Lý Trung Tâm & Đồng Bộ"]
        Converter[Bộ Chuyển Đổi Định Dạng & Chuẩn Hóa Schema]
        Fetcher[Bộ Khám Phá Model Qua REST API<br/><i>Chuẩn OpenAI / Anthropic</i>]
        Catalog[Danh Mục Model Chuẩn Hóa<br/><i>Tự Động Khớp Context & Định Giá</i>]
        SoftDel[Trình Quản Lý Xóa Mềm<br/><i>Lưu Riêng Biệt Phân Quyền 0600</i>]
        UndoRedo[Ngăn Xếp Hoàn Tác Transactional<br/><i>Lưu Trữ 100 Bước Thay Đổi</i>]
    end

    subgraph Validation ["3. Xác Thực & Kiểm Định"]
        SchemaValidator{Bộ Kiểm Tra JSON Schema<br/><i>Draft-07 & Fallback AST Parser</i>}
        SanityCheck[Kiểm Tra Toàn Vẹn Cấu Trúc File]
    end

    subgraph Persistence ["4. Lưu Trữ An Toàn & Đích Tệp Phân Lớp"]
        AtomicWriter[Trình Ghi File Atomic<br/><i>Ghi File Tạm -> Đổi Tên Nguyên Tử</i>]
        
        subgraph OpenCode_Targets ["Tệp Đích OpenCode"]
            OC_Global["~/.config/opencode/opencode.json & tui.json"]
            OC_Local[".opencode/opencode.json & tui.json"]
        end
        
        subgraph OpenClaude_Targets ["Tệp Đích OpenClaude Phân Tầng"]
            Policy["Chính Sách Doanh Nghiệp (Chỉ Đọc)<br/>/etc/claude-code/managed-settings.json"]
            User["Tầng Người Dùng (User)<br/>~/.openclaude/settings.json"]
            Project["Tầng Dự Án (Project)<br/>.openclaude/settings.json"]
            Local["Ghi Đè Cục Bộ (Local)<br/>.openclaude/settings.local.json"]
            GlobalApp["Trạng Thái Ứng Dụng & Hồ Sơ<br/>~/.openclaude.json & .mcp.json"]
        end
    end

    FormTabs <--> UndoRedo
    FormTabs <--> SecretMask
    FormTabs <--> InheritHint
    RawTab <--> SchemaValidator
    
    FormTabs --> Converter
    Fetcher --> Catalog
    Catalog --> Converter
    
    Converter --> SchemaValidator
    SchemaValidator --> SanityCheck
    SanityCheck -- Hợp Lệ --> AtomicWriter
    SanityCheck -- Lỗi Cú Pháp --> Reject[Từ Chối Ghi & Cảnh Báo]

    AtomicWriter --> OC_Global
    AtomicWriter --> OC_Local
    AtomicWriter --> User
    AtomicWriter --> Project
    AtomicWriter --> Local
    AtomicWriter --> GlobalApp
    Policy -. Đọc Giá Trị Kế Thừa .-> InheritHint
```

---

## 🚀 Tính Năng Chính & Năng Lực Chi Tiết

### 🛡️ An Toàn Dữ Liệu & Bảo Mật
- **Che Dấu Secret Zero-Leak**: Mọi API key, token và auth headers đều được ẩn dưới dạng `sk-****e`. Chỉ khi bấm vào nút 👁 giá trị mới được giải mã hiển thị.
- **Ghi File Atomic (Nguyên Tử)**: Dữ liệu được ghi vào file tạm trước khi thay thế file gốc, ngăn ngừa 100% tình trạng hỏng cấu hình khi mất điện hoặc tắt đột ngột.
- **Bảo Toàn Khóa Tuyệt Đối**: Mọi trường dữ liệu hoặc schema mở rộng chưa có giao diện form vẫn được giữ nguyên vẹn từng byte khi lưu.
- **Xóa Mềm Provider Bảo Mật**: Provider khi xóa sẽ được chuyển vào `~/.config/opencode-config-editor/deleted-providers.json` với phân quyền chặt chẽ `0600`, cho phép khôi phục nhanh chóng mà không để lộ key trong repo git.

### 🤖 Tính Năng Dành Riêng Cho OpenCode (10 Tab Chuyên Biệt)
- **Danh Sách Tab Đầy Đủ**: `General`, `Runtime`, `Agents`, `Commands`, `Providers`, `MCP Servers`, `Plugins`, `Permissions`, `TUI`, `Raw JSON`.
- **Lấy Danh Sách Model Từ API**:
  - Tự động quét và lấy danh sách model trực tiếp từ endpoint OpenAI/Anthropic của provider.
  - Tự động đối soát với danh mục catalog để điền dung lượng context, max token và pricing.
  - Phân biệt trạng thái `new` và `existing`, tùy chọn xóa sạch các model không còn hỗ trợ (`Sync`).
- **Thao Tác Hàng Loạt & Hoàn Tác**: Bật/tắt nhanh hàng loạt MCP server/plugin và hỗ trợ Undo/Redo tới 100 thao tác.

### ⚡ Tính Năng Dành Riêng Cho OpenClaude / Claude Code (8 Tab & 4 Phạm Vi MCP)
- **Phân Tầng Cấu Hình Rõ Ràng**:
  1. `Enterprise Policy` (Chỉ đọc, ưu tiên cao nhất, `/etc/claude-code/managed-settings.json`)
  2. `Local Overrides` (`.openclaude/settings.local.json`)
  3. `Project Scope` (`.openclaude/settings.json`)
  4. `User Defaults` (`~/.openclaude/settings.json`)
  5. `Global App State` (`~/.openclaude.json`)
- **Hiển Thị Giá Trị Kế Thừa**: Placeholder màu xám thể hiện giá trị kế thừa từ tầng trên giúp dễ dàng nhận biết nguồn gốc cài đặt.
- **Quản Lý 4 Phạm Vi MCP Toàn Diện**: Thiết lập MCP server trên cả 4 scope: `user`, `project` (`.mcp.json`), `local`, và `policy`.
- **Quản Lý Hooks & Quyền Hạn**: Trình thiết lập trực quan cho các sự kiện hook, matcher, timeout và ma trận phân quyền thực thi lệnh (`allow`/`deny`/`ask`).

---

## 🛠️ Công Nghệ & Yêu Cầu Hệ Thống

### Ngăn Xếp Công Nghệ (Tech Stack)
- **Ngôn ngữ**: Python 3.8+
- **Giao diện GUI**: PySide6 (Qt 6 for Python)
- **Kiểm định Schema**: `jsonschema` (Draft-07) kết hợp fallback AST engine
- **Đóng gói**: Script AST inliner độc lập (`build.py`) tạo file chạy duy nhất
- **Công cụ phát triển**: `ruff`, `pytest`, `pytest-cov`

### Yêu Cầu Hệ Thống
- **Hệ điều hành**: Linux (X11/Wayland), macOS (11+), Windows (10/11)
- **Python**: Phiên bản 3.8, 3.9, 3.10, 3.11, 3.12, 3.13
- **Thư viện phụ thuộc**: `PySide6 >= 6.0.0`, `jsonschema >= 4.0.0` (tùy chọn nhưng khuyến nghị)

---

## 📦 Hướng Dẫn Cài Đặt

### Cách 1: Cài Tự Động Bản Mới Nhất (Khuyến Nghị cho Linux)

Cài đặt trực tiếp vào thư mục `/opt/opencode-editor/` và tự động tạo biểu tượng ứng dụng trong menu:

```bash
curl -fsSL https://raw.githubusercontent.com/yana-arch/opencode-config-editor/master/install.sh | sudo bash
```

Hoặc tải script về chạy thủ công:
```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/yana-arch/opencode-config-editor/master/install.sh
sudo bash install.sh --remote
```

### Cách 2: Cài Từ File Đóng Gói Có Sẵn

```bash
python3 build.py
sudo bash install.sh --local opencode-config-editor.py
```

### Cách 3: Chạy Trực Tiếp Từ Mã Nguồn

```bash
# Clone mã nguồn
git clone https://github.com/yana-arch/opencode-config-editor.git
cd opencode-config-editor

# Cài đặt thư viện
pip install -r requirements.txt

# Khởi chạy ứng dụng
python3 src/app/main.py

# Hoặc build và chạy file standalone
python3 build.py
python3 opencode-config-editor.py
```

---

## 💻 Hướng Dẫn Sử Dụng & Phím Tắt

Khởi chạy ứng dụng từ terminal hoặc menu desktop:

```bash
# Khởi chạy chế độ mặc định (OpenCode)
opencode-editor

# Chuyển đổi sang chế độ OpenClaude
opencode-editor --adapter=openclaude
CONFIG_EDITOR_ADAPTER=openclaude opencode-editor
```

### Bảng Phím Tắt Tiện Dụng

| Thao Tác | Phím Tắt | Mô Tả |
| :--- | :--- | :--- |
| **Mở Thư Mục / File** | <kbd>Ctrl</kbd> + <kbd>O</kbd> | Mở workspace dự án hoặc file cấu hình cụ thể |
| **Lưu Thay Đổi** | <kbd>Ctrl</kbd> + <kbd>S</kbd> | Xác thực schema và ghi atomic toàn bộ thay đổi |
| **Hoàn Tác (Undo)** | <kbd>Ctrl</kbd> + <kbd>Z</kbd> | Khôi phục lại trạng thái cấu hình trước đó |
| **Làm Lại (Redo)** | <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Z</kbd> | Thực hiện lại thao tác vừa hoàn tác |
| **Chuyển Đổi Theme** | <kbd>Ctrl</kbd> + <kbd>T</kbd> | Đổi qua lại giữa giao diện Tối / Sáng / Theo Hệ Thống |
| **Phóng To / Thu Nhỏ** | <kbd>Ctrl</kbd> + <kbd>+</kbd> / <kbd>-</kbd> | Tùy chỉnh cỡ chữ giao diện |

---

## 🗂️ Cấu Trúc Thư Mục Dự Án

```text
opencode-config-editor-project/
├── build.py                      # Script đóng gói mã nguồn thành file thực thi duy nhất
├── install.sh                    # Script cài đặt hệ thống Linux & tạo desktop entry
├── requirements.txt              # Danh sách thư viện phụ thuộc
├── ruff.toml                     # Cấu hình linter và quy chuẩn code
├── CHANGELOG.md / CHANGELOG_EN.md# Lịch sử phiên bản
├── CONTRIBUTING.md               # Hướng dẫn đóng góp mã nguồn
├── src/
│   ├── app/
│   │   ├── main.py               # Điểm khởi chạy CLI và parse tham số
│   │   └── main_window.py        # Cửa sổ chính Qt, quản lý tab và phím tắt
│   ├── core/
│   │   ├── adapter.py            # Giao diện adapter và registry đăng ký agent
│   │   ├── base_tab.py           # Lớp cơ sở hỗ trợ dựng form và liên kết widget
│   │   ├── catalog.py            # Danh mục model và chuẩn hóa thông số nhà cung cấp
│   │   ├── config.py             # Quản lý đọc/ghi cấu hình phân tầng và ghi file atomic
│   │   ├── config_converter.py   # Bộ chuyển đổi schema giữa các định dạng
│   │   ├── connectivity.py       # Kiểm tra kết nối và độ trễ mạng tới endpoint
│   │   ├── header.py             # Hằng số toàn cục và định nghĩa kiểu
│   │   ├── mcp_templates.py      # Mẫu thiết lập sẵn cho các MCP server phổ biến
│   │   ├── parsing.py            # Trình phân tích cú pháp JSON / JSONC chịu lỗi
│   │   ├── provider_fetch.py     # Worker nền lấy danh sách model qua REST API
│   │   ├── settings.py           # Lưu trữ cài đặt giao diện (theme, font, vị trí cửa sổ)
│   │   ├── widgets_catalog.py    # Giao diện duyệt và lọc danh mục model
│   │   ├── widgets_common.py     # Widget dùng chung: MaskedLineEdit, status chips, badges
│   │   ├── widgets_connectivity.py# Hộp thoại kiểm tra kết nối API
│   │   ├── widgets_converter.py  # Hộp thoại chuyển đổi định dạng cấu hình
│   │   └── widgets_mcp_hub.py    # Trung tâm cài đặt & quản lý MCP server
│   └── adapters/
│       ├── opencode/             # Adapter cho OpenCode (10 tab chuyên dụng)
│       └── openclaude/           # Adapter cho OpenClaude (8 tab đa tầng + 4 scope MCP)
├── tests/                        # Bộ kiểm thử tự động pytest
├── opencode-config-editor.py     # Bản build độc lập (mặc định OpenCode)
└── openclaude-config-editor.py   # Bản build độc lập (mặc định OpenClaude)
```

---

## 📄 Bản Quyền & Tác Giả

Dự án phát hành theo giấy phép mã nguồn mở **MIT License**. Xem chi tiết tại [`LICENSE`](./LICENSE).

Phát triển và duy trì bởi **[yana-arch](https://github.com/yana-arch)**. Mọi đóng góp, báo cáo lỗi và đề xuất tính năng xin vui lòng gửi qua GitHub Issues và Pull Requests.
