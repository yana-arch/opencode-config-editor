# Changelog

[English Version](./CHANGELOG_EN.md) | **Tiếng Việt**

---
[← Quay lại README](README.md)

Tất cả các thay đổi đáng chú ý của dự án được ghi lại trong file này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/),
và dự án tuân theo [Semantic Versioning](https://semver.org/lang/vi/).

## [4.4.0] - 2026-08-23

Hỗ trợ agent thứ hai: **openclaude** (settings.json phân lớp), qua tầng adapter mới.

### Added

- **Adapter openclaude** — `build.py` giờ tạo **2 file chạy độc lập** từ cùng mã nguồn:
  `opencode-config-editor.py` (mặc định opencode) và `openclaude-config-editor.py`
  (mặc định openclaude). Đổi adapter khi chạy: `--adapter=openclaude` hoặc biến môi
  trường `CONFIG_EDITOR_ADAPTER`.
- **Cấu hình phân lớp**: user → project → local (lớp sau ghi đè lớp trước), cộng lớp
  **policy chỉ đọc** `managed-settings.json` (+ drop-in `managed-settings.d/*.json`)
  có ưu tiên cao nhất. Ô nhập hiện giá trị kế thừa dạng placeholder xám.
- **8 tab openclaude**: Settings, Agent Models, MCP, Plugins, Hooks, Permissions,
  Env & Limits, Raw (theo lớp).
- **MCP đủ 4 scope**: `user` → `~/.openclaude.json`, `project` → `.mcp.json`,
  `local` → `projects[<đường dẫn>].mcpServers`, `policy` → `managed-mcp.json` (chỉ đọc).
  Sửa được transport stdio/http, command/url, args, env, headers.
- **Plugins/marketplaces**: `enabledPlugins`, `extraKnownMarketplaces`
  (github/git/url/file/directory/npm kèm ref, autoUpdate), liệt kê marketplace đã cache.
- **Hooks có cấu trúc**: mỗi dòng là một hook entry (event · matcher · type ·
  command/url/prompt · timeout); event không đụng tới giữ nguyên từng byte.
- **Provider profiles**: `providerProfiles` với apiKey được che, chọn provider đang hoạt
  động (`activeProviderProfileId`), fallback chain, agent routing.
- **Che secret cho env/headers của MCP** — thường chứa API key, mask mặc định, bấm 👁 để xem.
- **Cảnh báo mất dữ liệu**: đổi lớp cấu hình khi còn thay đổi chưa lưu sẽ hỏi
  Save / Discard / Cancel (áp dụng cho cả buffer của tab Raw).
- **Editor cho `permissions`**: 4 danh sách rule (`allow`/`deny`/`ask`/
  `additionalDirectories`), `defaultMode` (gồm cả `manual`/`delegate`/`dontAsk` chưa
  tài liệu hoá), và 2 cờ `disableBypassPermissionsMode`/`disableAutoMode`; sub-key lạ
  được giữ nguyên.
- **Editor cho `env` và `modelLimits`**: env với giá trị được che, modelLimits sửa
  `contextWindow`/`maxOutputTokens` theo từng model và giữ nguyên sub-key lạ.
- **Kiểm tra trực tiếp trong tab Raw**: lỗi cấu trúc (đỏ) và cảnh báo key lạ / schema
  chính thức `claude-code-settings.json` (cam), tính theo từng lớp — riêng
  `~/.openclaude.json` không cảnh báo key lạ vì phần lớn là trạng thái ứng dụng.
  Cảnh báo không bao giờ chặn lưu.
- **Chặn ghi đè file JSON lỗi**: file tồn tại nhưng sai cú pháp sẽ không bị form ghi đè
  bằng `{}` — báo lỗi và hướng dẫn sửa ở tab Raw.

### Changed

- **Tầng adapter dùng chung** (`core/adapter.py`): `AdapterSpec` + registry cho targets,
  tabs, known keys và session hook (initial_load / refresh / save). opencode được chuyển
  sang dùng đúng tầng này, hành vi không đổi.
- `BaseTab` thêm helper dùng chung: `_set_text`, `cell_text`, `remove_current`,
  `preserve`/`preserved` — gộp code lặp giữa các tab.
- `atomic_write_json()` tách ra `core/config.py`, dùng chung cho cả `ConfigFile.save` và
  ghi file phân lớp; file tạm được dọn khi lỗi.
- Bộ key openclaude đối chiếu trực tiếp với `SettingsSchema` trong binary openclaude
  v0.28.0 và schema chính thức `claude-code-settings.json` (159 key).

### Fixed

- Không còn ghi đè trạng thái ứng dụng trong `~/.openclaude.json` (`numStartups`,
  `tipsHistory`, `projects`…) khi lưu provider/MCP.
- `MaskedLineEdit` không còn nuốt nội dung người dùng vừa gõ khi đang ở chế độ che, và
  nút 👁 không ghi đè nội dung đang sửa.
- Hooks: thêm dòng mới không còn bị mất do so trùng theo giá trị; xoá hết entry cũ rồi
  thêm mới không còn làm mất cả event.
- Bỏ editor MCP trùng lặp còn sót trong tab Agent Models (có thể ghi đè server đã sửa ở
  tab MCP).
- Sửa ô trong bảng (row đã có) giờ đánh dấu dirty đúng — trước đó thay đổi có thể bị bỏ qua
  khi lưu.
- Tên provider trùng nhau giờ được báo trên thanh trạng thái thay vì bị bỏ im lặng.
- Lưu bằng form khi tab Raw còn nội dung chưa lưu sẽ báo rõ là phần Raw KHÔNG được lưu.
- Bổ sung `skipFullAccessModePermissionPrompt` vào bộ key đã biết (có thật trong binary) —
  trước đó chính output của editor bị cảnh báo là key lạ.

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
