# Hướng dẫn đóng góp

[English Version](./CONTRIBUTING_EN.md) | **Tiếng Việt**

---
[← Quay lại README](README.md)

Cảm ơn bạn đã quan tâm đóng góp cho **opencode-config-editor**!

## Cấu trúc mã nguồn

Mã nguồn được chia thành các module trong thư mục `src/`, sau đó ghép lại thành một
file duy nhất bằng `build.py`. **Quan trọng**: chỉ sửa code trong `src/` — file
`opencode-config-editor.py` là đầu ra của build và sẽ bị ghi đè. Thứ tự ghép là
danh sách `ORDER` trong `build.py`.

```
src/core/                  # dùng chung, không phụ thuộc agent
  header.py                # Import, hằng số, danh sách key
  settings.py              # SettingsManager, ThemeManager, UndoManager
  config.py                # ConfigFile, Validator, section(), helper layered-config
  parsing.py               # helper import/parse/merge
  catalog.py               # ModelCatalog, ModelFormat, match/fallback
  provider_fetch.py        # fetch danh sách model từ provider
  adapter.py               # AdapterSpec + registry (điểm nối đa-agent)
  widgets_common.py        # widget/dialog dùng chung
  base_tab.py              # BaseTab: touched-tracking + helper set giá trị
  widgets_models.py        # dialog chỉnh sửa model
  widgets_catalog.py       # dialog catalog
src/adapters/opencode/     # phần riêng của opencode + tui
  tab_*.py                 # 10 tab
  adapter.py               # đăng ký AdapterSpec của opencode
src/app/                   # cửa sổ + entrypoint
  main_window.py           # MainWindow (điều khiển qua adapter)
  main.py                  # entrypoint
```

## Thêm một agent CLI mới (adapter)

Editor hỗ trợ đa-agent qua `core/adapter.py`. Để hỗ trợ CLI khác:

1. Tạo `src/adapters/<agent>/` với các class tab kế thừa `BaseTab`
   (triển khai `refresh()`/load và `collect(self, data)`).
2. Thêm `src/adapters/<agent>/adapter.py` gọi `register_adapter(AdapterSpec(...))`
   khai báo `kinds`, `known_keys`, `raw_files`, `targets_fn`, `make_tabs_fn`,
   `capabilities` của agent đó.
3. Thêm các file mới vào `ORDER` trong `build.py` (sau `core/*`, trước `app/*`).
4. Chọn adapter trong `app/main.py` (`--adapter`/env).

Không cần sửa `core/`. Contract test parametrize trong `tests/test_adapter.py`
tự động phủ mọi adapter đã đăng ký.

## Quy trình đóng góp

1. **Mở issue** mô tả bug hoặc tính năng bạn muốn thêm.
2. **Fork** repository và tạo branch riêng:
   ```bash
   git checkout -b feature/ten-tinh-nang
   ```
3. Sửa code trong `src/`, giữ đúng phong cách hiện tại (Python, 4-space indent,
   docstring ngắn gọn).
4. Build và kiểm tra:
   ```bash
   python3 build.py
   python3 opencode-config-editor.py
   ```
5. Cập nhật [CHANGELOG.md](CHANGELOG.md) nếu thay đổi đáng chú ý.
6. Tạo **Pull Request** và mô tả rõ thay đổi.

## Phong cách code

- Python 3.8+, tuân thủ [PEP 8](https://peps.python.org/pep-0008/).
- Docstring tiếng Anh (khớp với code hiện tại), ngắn gọn.
- Không thêm comment thừa; đặt tên hàm/biến rõ nghĩa.
- Khi thêm tính năng UI, cập nhật danh sách tab/key trong `00_header.py` nếu cần.

## Các bước thông thường khi thêm tab mới

1. Tạo class tab (kế thừa `BaseTab`) trong adapter tương ứng,
   ví dụ `src/adapters/opencode/tab_tinhnang.py`.
2. Triển khai `refresh()`/load và `collect(self, data)`.
3. Thêm vào `make_tabs_fn` của adapter trong `adapters/<agent>/adapter.py`
   (thêm `(tab, "Tiêu đề", kind)`); tab opencode.json thì thêm vào `win._oc_tabs`.
4. Thêm file mới vào `ORDER` trong `build.py`.

## Báo cáo bug

Khi báo bug, hãy cung cấp:

- Phiên bản Python và PySide6 (`python3 -c "import PySide6; print(PySide6.__version__)"`).
- Hệ điều hành và desktop environment.
- Các bước tái hiện lỗi và thông báo lỗi (nếu có).
- Mẫu cấu hình gây lỗi (đã loại bỏ dữ liệu nhạy cảm).

## Ghi chú

Vui lòng không commit dữ liệu nhạy cảm (API key, token) trong cấu hình mẫu hay code.
