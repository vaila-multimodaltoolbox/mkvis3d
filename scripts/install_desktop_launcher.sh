#!/usr/bin/env bash
# Installs mkvis3d desktop entry with the vailá icon into the user's application menu
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$(uname)" = "Darwin" ]; then
    exec "$DIR/scripts/install_macos.sh" "$@"
fi

ICON_PATH="$DIR/assets/icons/vaila_512x512.png"
if [ ! -f "$ICON_PATH" ]; then
    ICON_PATH="$DIR/assets/icons/vaila.png"
fi

EXEC_PATH="$DIR/mkvis3d_launcher.sh"
if [ -f "$DIR/dist/mkvis3d" ]; then
    EXEC_PATH="$DIR/dist/mkvis3d"
fi

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APP_DIR"

DESKTOP_FILE="$APP_DIR/mkvis3d.desktop"
cat << DESKTOP_CONTENT > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=mkvis3d
GenericName=Motion Analysis & 3D Viewer
Comment=OpenBiomech 3D Motion Analysis and Visualization Suite
Exec="$EXEC_PATH"
Icon=$ICON_PATH
Terminal=false
Categories=Science;Education;Graphics;AudioVideo;
StartupNotify=true
MimeType=application/x-c3d;text/csv;
DESKTOP_CONTENT

chmod +x "$DESKTOP_FILE"
echo "Installed desktop entry at $DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
fi

echo "mkvis3d is now available in your application menu with the vailá icon!"
