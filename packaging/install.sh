#!/usr/bin/env bash
# Per-user install: private virtualenv, launcher in ~/.local/bin, menu entry.
# Usage: ./packaging/install.sh [--uninstall]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ns2gen"
BIN_DIR="$HOME/.local/bin"
DESK_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -rf "$APP_DIR" "$BIN_DIR/ns2gen" "$DESK_DIR/ns2gen.desktop" "$ICON_DIR/ns2gen.svg"
    echo "ns2gen removed."
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
if ! python3 -c "import tkinter" 2>/dev/null; then
    cat <<'EOF'
Tkinter is missing. Install it first:
  Debian/Ubuntu: sudo apt install python3-tk python3-venv
  Fedora:        sudo dnf install python3-tkinter
  Arch:          sudo pacman -S tk
  openSUSE:      sudo zypper install python3-tk
EOF
    exit 1
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESK_DIR" "$ICON_DIR"
python3 -m venv "$APP_DIR/venv" || { echo "venv failed (Debian/Ubuntu: sudo apt install python3-venv)"; exit 1; }
"$APP_DIR/venv/bin/pip" install --quiet --upgrade "$SRC"

ln -sf "$APP_DIR/venv/bin/ns2gen" "$BIN_DIR/ns2gen"
cp "$SRC/packaging/ns2gen.svg" "$ICON_DIR/ns2gen.svg"
sed "s|^Exec=.*|Exec=$APP_DIR/venv/bin/ns2gen|" "$SRC/packaging/ns2gen.desktop" > "$DESK_DIR/ns2gen.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$DESK_DIR" || true

echo "Installed. Run 'ns2gen' (make sure $BIN_DIR is in your PATH) or use the app menu."
