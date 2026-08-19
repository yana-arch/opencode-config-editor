#!/bin/bash
set -euo pipefail

APP_NAME="opencode-editor"
INSTALL_DIR="/opt/$APP_NAME"
VERSION="4.0.0"
SOURCE_FILE="opencode-config-editor.py"

echo "Đang cài đặt $APP_NAME v$VERSION..."

# 1. Kiểm tra quyền root
if [[ $EUID -ne 0 ]]; then
  echo "Vui lòng chạy script này với quyền sudo (ví dụ: sudo bash install.sh)."
  exit 1
fi

# 2. Cài đặt Python và PySide6 (Dependencies)
echo "Đang kiểm tra và cài đặt phụ thuộc hệ thống..."
if command -v pacman &> /dev/null; then
    echo "OK"
    # pacman -S python python3-pyside6
elif command -v apt &> /dev/null; then
    apt update && apt install -y python3 python3-pyside6
elif command -v dnf &> /dev/null; then
    dnf install -y python3 python3-pyside6
else
    echo "Cảnh báo: Không tìm thấy trình quản lý gói phổ biến. Hãy cài đặt python3-pyside6 thủ công."
fi

# 3. Thiết lập thư mục cài đặt
echo "Đang thiết lập thư mục tại $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
mkdir -p "/usr/local/bin"

# Copy file v4 vào thư mục cài đặt
if [[ -f "$SOURCE_FILE" ]]; then
    cp "$SOURCE_FILE" "$INSTALL_DIR/main.py"
    echo "Đã copy $SOURCE_FILE vào hệ thống."
else
    echo "Lỗi: Không tìm thấy file $SOURCE_FILE. Hãy đảm bảo bạn đang chạy script này bên trong thư mục chứa code."
    exit 1
fi

chmod +x "$INSTALL_DIR/main.py"

# 4. Tạo script khởi chạy nhanh (Wrapper)
echo "Đang tạo lệnh khởi chạy nhanh '/usr/local/bin/$APP_NAME'..."
cat << EOF > /usr/local/bin/$APP_NAME
#!/bin/bash
python3 $INSTALL_DIR/main.py "\$PWD"
EOF
chmod +x /usr/local/bin/$APP_NAME

# 5. Tạo Shortcut ứng dụng (.desktop)
echo "Đang tạo Shortcut trong Menu ứng dụng..."
cat << EOF | tee /usr/share/applications/$APP_NAME.desktop > /dev/null
[Desktop Entry]
Name=OpenCode Config Editor
Comment=Chỉnh sửa cấu hình opencode.json và tui.json
Exec=$APP_NAME
Icon=preferences-system
Terminal=false
Type=Application
Categories=Development;Settings;
Keywords=opencode;config;json;
EOF

echo "-------------------------------------------------------"
echo "Cài đặt hoàn tất thành công!"
echo "Cách sử dụng:"
echo "1. Mở Terminal và gõ: $APP_NAME"
echo "2. Hoặc tìm 'OpenCode Config Editor' trong danh sách ứng dụng."
echo "-------------------------------------------------------"
