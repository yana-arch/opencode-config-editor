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
# Tuỳ chọn (truyền dạng cờ để hoạt động qua sudo — sudo không giữ biến môi trường):
#   sudo bash install.sh --remote --repo <owner/repo>   # đổi nguồn tải (mặc định yana-arch/opencode-config-editor)
#   sudo bash install.sh --remote --version <x.y.z>      # cài phiên bản cụ thể thay vì mới nhất
#   sudo bash install.sh --remote --no-deps              # bỏ qua cài python3/pyside6
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
Cách dùng: bash install.sh [--remote | --local <file>] [tuỳ chọn]

  --remote               Tải release từ GitHub (mặc định)
  --local <file>         Cài từ file python có sẵn trong thư mục
  --repo <owner/repo>    Đổi nguồn tải remote (mặc định: yana-arch/opencode-config-editor)
  --version <x.y.z>      Cài phiên bản cụ thể (mặc định: latest)
  --no-deps              Bỏ qua cài đặt phụ thuộc (python3, pyside6)
  -h, --help             Hiển thị trợ giúp này

Các cờ trên hoạt động cả khi chạy qua sudo. Biến môi trường REPO/VERSION/NO_DEPS
vẫn được hỗ trợ khi KHÔNG dùng sudo.
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
            --no-deps)
                NO_DEPS="1"
                shift
                ;;
            --repo)
                shift
                [[ $# -gt 0 && "$1" != --* ]] || die "--repo cần giá trị <owner/repo>."
                REPO="$1"
                shift
                ;;
            --version)
                shift
                [[ $# -gt 0 && "$1" != --* ]] || die "--version cần giá trị <x.y.z>."
                VERSION="$1"
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
    echo "Đang cài phụ thuộc: python3, PySide6..."
    # Install per-package with --needed so a single wrong name or an
    # already-present package can't abort the whole script (set -e).
    local failed=""
    if have pacman; then
        pacman -S --needed --noconfirm python || failed+=" python"
        pacman -S --needed --noconfirm pyside6 || failed+=" pyside6"
    elif have apt; then
        apt update || true
        apt install -y python3 || failed+=" python3"
        apt install -y python3-pyside6 || failed+=" python3-pyside6"
    elif have dnf; then
        dnf install -y python3 || failed+=" python3"
        dnf install -y python3-pyside6 || failed+=" python3-pyside6"
    elif have zypper; then
        zypper --non-interactive install python3 || failed+=" python3"
        zypper --non-interactive install python3-PySide6 || failed+=" python3-PySide6"
    else
        echo "Cảnh báo: Không tìm thấy trình quản lý gói. Hãy tự cài python3 và PySide6" \
             "(pip install --user PySide6), rồi chạy lại với --no-deps."
        return
    fi
    if [[ -n "$failed" ]]; then
        echo "Cảnh báo: không cài được:$failed. Hãy tự cài (ví dụ Arch: 'pacman -S python pyside6';" \
             "hoặc 'pip install --user PySide6'), rồi chạy lại với --no-deps nếu cần."
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

    # XDG-style config directory for the app
    # If run via sudo, SUDO_USER gives the original user
    local target_user="${SUDO_USER:-$USER}"
    local user_home
    user_home=$(getent passwd "$target_user" | cut -d: -f6)
    local config_dir="$user_home/.config/opencode-config-editor"

    echo "Đang khởi tạo thư mục cấu hình tại $config_dir ..."
    mkdir -p "$config_dir"
    # Chown the directory itself even when no group is named after the user:
    # "user:user" fails with 'invalid group' on such systems and the old
    # `|| true` swallowed it, leaving a root-owned dir that crashes startup.
    chown -R "$target_user" "$config_dir" 2>/dev/null \
        || die "Không thể đặt quyền sở hữu cho $config_dir. Hãy chạy: sudo chown -R $target_user \"$config_dir\""

    # Copy catalog nếu có sẵn trong repo
    local cat_src="models/models.dev.catalog.json"
    if [[ -f "$cat_src" ]]; then
        echo "Đang cài đặt model catalog..."
        cp "$cat_src" "$config_dir/catalog.json"
        chown "$target_user" "$config_dir/catalog.json" 2>/dev/null || true
    fi

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