# Hướng dẫn đóng góp

[English Version](./CONTRIBUTING_EN.md) | **Tiếng Việt**

---
[← Quay lại README](README.md)

Cảm ơn bạn đã quan tâm đóng góp cho **opencode-config-editor**!

## Cấu trúc mã nguồn

Mã nguồn được chia thành các module trong thư mục `src/`, sau đó ghép lại thành một
file duy nhất bằng `build.py`. **Quan trọng**: chỉ sửa code trong `src/` — file
`opencode-config-editor.py` là đầu ra của build và sẽ bị ghi đè.

```
src/00_header.py    # Import, hằng số, danh sách key
src/01_core.py      # SettingsManager, ThemeManager, UndoManager, Validator, ModelCatalog…
src/02_widgets.py   # Widget/dialog dùng chung
src/03_tabs.py      # Các tab chỉnh sửa
src/04_main_window.py  # Cửa sổ chính
src/05_main.py      # Entrypoint
```

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

1. Tạo class tab (kế thừa `QWidget`) trong `src/03_tabs.py`.
2. Triển khai phương thức `_refresh`/load và `collect(self, data)`.
3. Đăng ký tab trong `MainWindow._build_tabs()` (`src/04_main_window.py`).
4. Nếu là tab opencode, thêm vào `self._oc_tabs`.

## Báo cáo bug

Khi báo bug, hãy cung cấp:

- Phiên bản Python và PySide6 (`python3 -c "import PySide6; print(PySide6.__version__)"`).
- Hệ điều hành và desktop environment.
- Các bước tái hiện lỗi và thông báo lỗi (nếu có).
- Mẫu cấu hình gây lỗi (đã loại bỏ dữ liệu nhạy cảm).

## Ghi chú

Vui lòng không commit dữ liệu nhạy cảm (API key, token) trong cấu hình mẫu hay code.
