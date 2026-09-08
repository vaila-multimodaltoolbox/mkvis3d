#!/usr/bin/env bash
# macOS Application (.app) build script using PyInstaller and uv
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "Building mkvis3d macOS Application Bundle (.app) with vaila.icns..."
uv run --with pyinstaller pyinstaller --clean -y mkvis3d.spec

if [ -d "$DIR/dist/mkvis3d.app" ]; then
    echo ""
    echo "Successfully built dist/mkvis3d.app"
fi
