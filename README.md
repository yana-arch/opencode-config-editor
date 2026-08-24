# opencode-config-editor

[English Version](./README_EN.md) | **Tiếng Việt**

Trình chỉnh sửa đồ họa (GUI) cho file cấu hình của các coding agent. Hỗ trợ hai agent:

- **[opencode](https://opencode.ai)** — `opencode.json` và `tui.json`
- **[openclaude](https://openclaude.gitlawb.com)** — `settings.json` phân lớp (user → project →
  local) + `~/.openclaude.json` + `.mcp.json`

Ứng dụng giúp chỉnh sửa cấu hình một cách trực quan, thay vì phải sửa JSON thủ công, với hỗ trợ
xác thực theo schema, import/export và nhiều tiện ích khác.

![Version](https://img.shields.io/badge/version-4.4.1-blue)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![GUI](https://img.shields.io/badge/GUI-PySide6-green)

## Tính năng

**Chung cho cả hai agent**
- **Xác thực schema** với báo cáo lỗi chi tiết (dùng `jsonschema` nếu có, kèm kiểm tra cơ bản).
- **Che (mask) giá trị bí mật** — API key, token, header xác thực chỉ hiện dạng `sk-****e`,
  bấm 👁 để xem. Giá trị thật không bao giờ lộ ra giao diện khi chưa mở.
- **Bảo toàn dữ liệu**: key mà giao diện chưa hỗ trợ vẫn được giữ nguyên khi lưu; lưu file
  theo cơ chế atomic (ghi tạm rồi thay thế); từ chối ghi đè file JSON đang lỗi cú pháp.
- **Cảnh báo trước khi mất dữ liệu**: hỏi Save/Discard/Cancel nếu đổi lớp cấu hình khi còn
  thay đổi chưa lưu.
- **Giao diện**: theme sáng/tối (theo hệ thống), điều chỉnh cỡ chữ, phím tắt thông dụng.
- **Raw JSON tab** với syntax highlighting và xác thực trực tiếp (debounced).

**Riêng cho opencode**
- **10 tab chuyên biệt**: General, Runtime, Agents, Commands, Providers, MCP Servers, Plugins,
  Permissions, TUI, Raw JSON.
- **Quản lý model nâng cao**: thêm/sửa/xóa model, chỉnh sửa hàng loạt (bulk edit), catalog model
  với preview và lọc.
- **Import/Export** provider, MCP server và plugin, kèm giải quyết xung đột.
- **Fetch model từ API của provider** — hai điểm vào:
  - Nút *+ Fetch from API* trên thanh công cụ tab **Providers**: **thêm provider mới** bằng
    cách nhập danh sách model từ endpoint (khoá provider có thể chỉnh trong dialog), kèm
    auto-match catalog qua một dialog xem trước (hỗ trợ reference provider + mapping đã lưu).
  - Nút *Fetch from API* trong dialog **Models** của từng provider (mở bằng *Models...*):
    **cập nhật model cho provider đã có**, điền sẵn `baseURL`/`apiKey` từ cấu hình.
  Cả hai đều tự lưu `options.baseURL` + `options.apiKey` và chọn `npm` phù hợp; cột **Status**
  đánh dấu `new`/`existing`, spec đã cấu hình không bị ghi đè, tuỳ chọn **Sync** để xoá model
  API không còn liệt kê, và model mới được normalize theo catalog ngay sau khi thêm.
- **Undo/redo** cho mọi thao tác (giới hạn 100 bước).
- **Bật/tắt hàng loạt** cho plugin và MCP server.

**Riêng cho openclaude** — xem chi tiết ở [mục openclaude](#openclaude)
- **8 tab**: Settings, Agent Models, MCP, Plugins, Hooks, Permissions, Env & Limits,
  Raw (theo từng lớp).
- Chỉnh sửa **cấu hình phân lớp** với gợi ý giá trị kế thừa và lớp chính sách (policy) chỉ đọc.
- **MCP đủ 4 scope**, **plugins/marketplaces**, **hooks** dạng bảng có cấu trúc.

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

### Cách 2: Cài từ file có sẵn

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

## openclaude

`build.py` tạo **hai** file chạy độc lập từ cùng một mã nguồn — khác nhau chỉ ở adapter mặc định:

| File | Agent mặc định |
| --- | --- |
| `opencode-config-editor.py` | opencode |
| `openclaude-config-editor.py` | openclaude |

Có thể đổi adapter khi chạy mà không cần build lại:

```bash
python3 opencode-config-editor.py --adapter=openclaude
CONFIG_EDITOR_ADAPTER=openclaude python3 opencode-config-editor.py
```

### Các file cấu hình openclaude

| File | Lớp (layer) | Nội dung |
| --- | --- | --- |
| `<managed>/managed-settings.json` | policy (chỉ đọc) | Chính sách doanh nghiệp, **ưu tiên cao nhất**. Kèm drop-in `managed-settings.d/*.json` và `managed-mcp.json`. Đường dẫn: `/etc/claude-code` (Linux), `/Library/Application Support/ClaudeCode` (macOS), `C:\Program Files\ClaudeCode` (Windows). |
| `~/.openclaude/settings.json` | user | Mặc định toàn máy |
| `.openclaude/settings.json` | project | Commit vào repo |
| `.openclaude/settings.local.json` | local | Ghi đè theo máy, thường gitignore |
| `~/.openclaude.json` | global | `providerProfiles`, `activeProviderProfileId`, `mcpServers` (scope user), và trạng thái ứng dụng (`numStartups`, `projects`…) — phần trạng thái **không bị ghi đè**. |
| `<project>/.mcp.json` | project-mcp | MCP server scope project |

Thứ tự merge: user → project → local, rồi **policy ghi đè tất cả**.
Thư mục cấu hình đổi được qua `OPENCLAUDE_CONFIG_DIR` (hoặc `CLAUDE_CONFIG_DIR` legacy).

### Các tab openclaude

- **Settings** — chọn lớp để sửa; `model`, `agent`, `effortLevel`, `advisorModel`, `statusLine`,
  các cờ bỏ qua nhắc quyền, và cổng chặn MCP (`enableAllProjectMcpServers`,
  `enabled/disabledMcpjsonServers`). Ô nhập hiện giá trị **kế thừa** dạng placeholder xám để
  biết giá trị nào đến từ lớp khác.
- **Agent Models** — `providerProfiles` (apiKey được che), chọn provider đang hoạt động, chuỗi
  fallback, agent routing.
- **MCP** — 4 scope: `user` → global, `project` → `.mcp.json`, `local` →
  `projects[file dict].mcpServers`, `policy` → chỉ đọc. Sửa được transport (stdio/http),
  command/url, **args**, env và headers (env/headers được che vì thường chứa API key).
- **Plugins** — `enabledPlugins`, `extraKnownMarketplaces` (github/git/url/file/directory/npm
  kèm ref và autoUpdate), liệt kê marketplace đã cache.
- **Hooks** — mỗi dòng là một hook entry: event · matcher · type · command/url/prompt · timeout.
  Sửa đúng chỗ: các event không đụng tới được giữ **nguyên từng byte**.
- **Permissions** — `permissions`: 4 danh sách rule (`allow`/`deny`/`ask`/
  `additionalDirectories`, mỗi dòng một rule kiểu `Bash(ls)`), `defaultMode`, và 2 cờ
  `disableBypassPermissionsMode`/`disableAutoMode`. Sub-key lạ được giữ nguyên.
- **Env & Limits** — `env` (giá trị được che vì thường chứa API key) và `modelLimits`
  (`contextWindow`/`maxOutputTokens` theo từng model; sub-key lạ giữ nguyên).
- **Raw (theo lớp)** — sửa trực tiếp JSON của từng lớp, gồm cả `.mcp.json`, kèm kiểm tra
  trực tiếp: lỗi JSON và lỗi kiểu dữ liệu hiện màu đỏ, key lạ / cảnh báo schema màu cam.

> **Mẹo**: nếu một tab trống, nó sẽ cho biết cấu hình đang nằm ở lớp nào
> (ví dụ *"No hooks in the 'project' layer. Hooks found in: user (6 entries)"*) — đổi
> **Edit layer** ở đầu tab là thấy.

## Cấu trúc dự án

```
.
├── src/
│   ├── core/                 # Generic, không phụ thuộc agent
│   │   ├── header.py         # Import, hằng số, key opencode
│   │   ├── settings.py       # QSettings, theme, undo
│   │   ├── config.py         # ConfigFile, LayeredConfig merge, atomic write
│   │   ├── adapter.py        # AdapterSpec + registry
│   │   ├── base_tab.py       # Helper dùng chung cho mọi tab form
│   │   └── widgets_*.py      # Widget/dialog dùng chung (gồm MaskedLineEdit)
│   ├── adapters/
│   │   ├── opencode/         # 10 tab + đăng ký adapter opencode
│   │   └── openclaude/       # constants, config phân lớp, 6 tab, adapter
│   └── app/                  # Cửa sổ chính + entrypoint
├── tests/                    # pytest (chạy tự động trong build.py)
├── build.py                  # Ghép src/ thành 2 file chạy độc lập
├── install.sh                # Script tải release từ GitHub và cài đặt
├── .github/workflows/        # GitHub Actions: build + release tự động
├── opencode-config-editor.py     # File đã build (adapter opencode)
├── openclaude-config-editor.py   # File đã build (adapter openclaude)
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

- **opencode**: lấy schema từ `https://opencode.ai/config.json` và `https://opencode.ai/tui.json`
  (cache trong `~/.cache/opencode-config-editor/`).
- **openclaude**: bộ 159 key đối chiếu với `SettingsSchema` trong binary openclaude v0.28.0,
  cộng schema chính thức `https://json.schemastore.org/claude-code-settings.json` (cache trong
  `~/.cache/openclaude-config-editor/`). Tab Raw báo lỗi kiểu dữ liệu (đỏ) và cảnh báo key
  lạ/schema (cam) theo từng lớp; riêng `~/.openclaude.json` không bị cảnh báo key lạ vì phần
  lớn là trạng thái ứng dụng.

Nếu không cài `jsonschema`, ứng dụng sẽ tự động chuyển sang bộ kiểm tra cơ bản dựa trên các key
đã biết. Trong cả hai trường hợp, key lạ **không bị xóa** — chỉ được báo là cảnh báo.

## Giấy phép

Xem [LICENSE](LICENSE).

---
**Tài liệu liên quan:**
- [Nhật ký thay đổi (Changelog)](CHANGELOG.md)
- [Hướng dẫn đóng góp (Contributing)](CONTRIBUTING.md)
