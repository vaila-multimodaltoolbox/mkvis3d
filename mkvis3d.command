#!/usr/bin/env bash
# macOS double-clickable launcher in Finder
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ -d "$DIR/dist/mkvis3d.app" ]; then
    open "$DIR/dist/mkvis3d.app"
elif [ -f "$DIR/dist/mkvis3d" ]; then
    exec "$DIR/dist/mkvis3d" "$@"
elif [ -f "$DIR/mkvis3d.py" ]; then
    exec "$DIR/mkvis3d.py" "$@"
elif command -v uv >/dev/null 2>&1; then
    exec uv run mkvis3d gui "$@"
else
    exec python3 -m openbiomech.cli gui "$@"
fi
