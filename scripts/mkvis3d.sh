#!/usr/bin/env bash
# Double-clickable launcher for mkvis3d (Linux)
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -f "$DIR/dist/mkvis3d" ]; then
    exec "$DIR/dist/mkvis3d" "$@"
elif command -v uv >/dev/null 2>&1; then
    exec uv run mkvis3d gui "$@"
else
    exec python3 -m openbiomech.cli gui "$@"
fi
