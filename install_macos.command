#!/usr/bin/env bash
# macOS double-clickable installation & Gatekeeper setup in Finder
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

exec "$DIR/scripts/install_macos.sh" "$@"
