#!/bin/bash
set -euo pipefail

# ============================================================
# opencode-config-editor installer
# Cài đặt từ file local hoặc tải release từ GitHub.
#
# Cách dùng:
#   # Remote (mặc định): tải release mới nhất từ GitHub
#   curl -fsSL https://raw.githubusercontent.com/yana-arch/opencode-config-editor/master/install.sh | sudo bash
#   sudo bash install.sh --remote
#
#   # Local: cài từ file python đã có sẵn trong thư mục
#   sudo bash install.sh --local opencode-config-editor.py
#
# Tuỳ biến:
#   REPO=<owner/repo>  bash install.sh    # đổi nguồn tải remote (mặc định yana-arch/opencode-config-editor)
#   VERSION=<x.y.z>    bash install.sh    # cài phiên bản cụ thể thay vì mới nhất
#   NO_DEPS=1          bash install.sh    # bỏ qua cài python3/pyside6
# ============================================================

APP_NAME="opencode-editor"
BIN_NAME="opencode-editor"
INSTALL_DIR="/opt/$APP_NAME"
DESKTOP_NAME="$APP_NAME.desktop"

# Mặc định
REPO="${REPO:-yana-arch/opencode-config-editor}"
VERSION="${VERSION:-latest}"
NO_DEPS="${NO_DEPS:-0}"
MODE="remote"
LOCAL_FILE=""

# ---------- Parser tham số ----------
usage() {
    cat <<EOF
Cách dùng: bash install.sh [--remote | --local <file>]

  --remote               Tải release từ GitHub (mặc định)
  --local <file>         Cài từ file python có sẵn trong thư mục
  -h, --help             Hiển thị trợ giúp này

Biến môi trường:
  REPO=<owner/repo>      Đổi nguồn tải remote (mặc định: yana-arch/opencode-config-editor)
  VERSION=<x.y.z>        Cài phiên bản cụ thể (mặc định: latest)
  NO_DEPS=1              Bỏ qua cài đặt phụ thuộc (python3, pyside6)
EOF
    exit "${1:-0}"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --remote)
                MODE="remote"
                shift
                ;;
            --local)
                MODE="local"
                shift
                if [[ $# -eq 0 || "$1" == --* ]]; then
                    die "Cần chỉ định file khi dùng --local (ví dụ: --local opencode-config-editor.py)."
                fi
                LOCAL_FILE="$1"
                shift
                ;;
            -h|--help)
                usage 0
                ;;
            *)
                die "Tham số không hợp lệ: $1 (dùng --help để xem trợ giúp)."
                ;;
        esac
    done
}

# ---------- Hàm ----------
die() {
    echo "Lỗi: $*" >&2
    exit 1
}

banner() {
    echo "========================================================"
    echo " opencode-config-editor — Installer"
    echo " Mode   : $MODE"
    if [[ "$MODE" == "remote" ]]; then
        echo " Repo   : $REPO"
        echo " Version: $VERSION"
    else
        echo " File   : $LOCAL_FILE"
    fi
    echo "========================================================"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        die "Vui lòng chạy script với quyền root (sudo bash install.sh)."
    fi
}

have() {
    command -v "$1" >/dev/null 2>&1
}

get_latest_version() {
    # Lấy tag mới nhất từ GitHub API
    local url="https://api.github.com/repos/$REPO/releases/latest"
    local tag
    tag=$(curl -fsSL "$url" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
    [[ -n "$tag" ]] || die "Không lấy được phiên bản mới nhất từ $url"
    echo "${tag#v}"
}

install_deps() {
    if [[ "$NO_DEPS" == "1" ]]; then
        echo "(bỏ qua cài phụ thuộc theo NO_DEPS=1)"
        return
    fi
    echo "Đang cài phụ thuộc: python3, python3-pyside6..."
    if have pacman; then
        pacman -Sy --noconfirm python python-pyside6
    elif have apt; then
        apt update && apt install -y python3 python3-pyside6
    elif have dnf; then
        dnf install -y python3 python3-pyside6
    elif have zypper; then
        zypper --non-interactive install python3 python3-PySide6
    else
        echo "Cảnh báo: Không tìm thấy trình quản lý gói. Hãy tự cài python3 và PySide6."
    fi
}

download() {
    # Tải file release về thư mục tạm. Hỗ trợ 'latest' hoặc phiên bản cụ thể.
    local ver="$1"
    local dest="$2"
    local tag="v$ver"
    local url
    if [[ "$ver" == "latest" ]]; then
        ver="$(get_latest_version)"
        tag="v$ver"
    fi
    url="https://github.com/$REPO/releases/download/$tag/opencode-config-editor-$ver.py"
    echo "Đang tải: $url"
    curl -fL --retry 3 -o "$dest" "$url" \
        || die "Tải file thất bại. Kiểm tra tag $tag và asset 'opencode-config-editor-$ver.py' có tồn tại."
}

install_files() {
    local src="$1"
    local keep="$2"   # "keep" giữ nguyên file nguồn (không xóa)
    mkdir -p "$INSTALL_DIR" /usr/local/bin
    cp "$src" "$INSTALL_DIR/main.py"
    chmod +x "$INSTALL_DIR/main.py"

    # Wrapper
    cat > /usr/local/bin/$BIN_NAME <<EOF
#!/bin/bash
exec python3 $INSTALL_DIR/main.py "\$PWD"
EOF
    chmod +x /usr/local/bin/$BIN_NAME

    # Shortcut .desktop
    cat > /usr/share/applications/$DESKTOP_NAME <<EOF
[Desktop Entry]
Name=OpenCode Config Editor
Name[vi]=Trình sửa cấu hình OpenCode
Comment=Edit opencode.json and tui.json
Exec=$BIN_NAME
Icon=preferences-system
Terminal=false
Type=Application
Categories=Development;Settings;
Keywords=opencode;config;json;
EOF

    if [[ "$keep" != "keep" ]]; then
        rm -f "$src"
    fi
}

# ---------- Chạy ----------
parse_args "$@"
banner
check_root

install_deps

case "$MODE" in
    remote)
        have curl || die "Cần 'curl' để tải release (cài: apt/pacman/dnf install curl)."
        echo "Đang chuẩn bị tải..."
        TMP_FILE="$(mktemp /tmp/$APP_NAME.XXXXXX.py)"
        trap 'rm -f "$TMP_FILE"' EXIT
        download "$VERSION" "$TMP_FILE"
        echo "Đang cài đặt vào $INSTALL_DIR ..."
        install_files "$TMP_FILE"
        ;;
    local)
        [[ -f "$LOCAL_FILE" ]] || die "Không tìm thấy file: $LOCAL_FILE"
        echo "Đang cài đặt từ file $LOCAL_FILE vào $INSTALL_DIR ..."
        install_files "$LOCAL_FILE" keep
        ;;
esac

echo "--------------------------------------------------------"
echo "Cài đặt hoàn tất!"
echo "Cách dùng:"
echo "  1. Gõ lệnh:  $BIN_NAME"
echo "  2. Hoặc tìm 'OpenCode Config Editor' trong menu ứng dụng."
echo "--------------------------------------------------------"