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
    cd "$DIR/dist"
    zip -r -q mkvis3d-macos-app.zip mkvis3d.app
    echo "Created dist/mkvis3d-macos-app.zip for GitHub Release distribution."
    echo ""
    echo "======================================================================"
    echo "⚠️  Instrução importante para os usuários de Mac (Gatekeeper / Quarentena):"
    echo "Como o app ainda não possui uma assinatura paga de desenvolvedor Apple (notarização):"
    echo "Quando o usuário baixar o .zip pelo navegador e descompactar o mkvis3d.app,"
    echo "o macOS bloqueará a execução dizendo que \"o app não pôde ser verificado\"."
    echo ""
    echo "Na descrição da sua Release e para usuários, adicione a instrução:"
    echo "  No macOS (primeira execução):"
    echo "  • Clique com o botão direito (ou Control + clique) sobre o mkvis3d.app e escolha Abrir (Open)."
    echo "  • Ou rode no Terminal:"
    echo "    xattr -cr mkvis3d.app"
    echo "======================================================================"
fi
