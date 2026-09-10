#!/usr/bin/env bash
# macOS installation & Gatekeeper quarantine unblocker for mkvis3d
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "======================================================================"
echo "🍎 mkvis3d — Instalação e Configuração macOS"
echo "======================================================================"

APP_TARGET=""
if [ -d "$DIR/dist/mkvis3d.app" ]; then
    APP_TARGET="$DIR/dist/mkvis3d.app"
elif [ -d "$DIR/mkvis3d.app" ]; then
    APP_TARGET="$DIR/mkvis3d.app"
elif [ -d "/Applications/mkvis3d.app" ]; then
    APP_TARGET="/Applications/mkvis3d.app"
fi

if [ -n "$APP_TARGET" ]; then
    echo "Aplicativo encontrado em: $APP_TARGET"
    echo "Limpando atributo de quarentena do macOS (Gatekeeper)..."
    xattr -cr "$APP_TARGET" 2>/dev/null || true
    echo "✅ Quarentena removida com sucesso!"

    if [ "$1" = "--applications" ] && [ "$APP_TARGET" != "/Applications/mkvis3d.app" ]; then
        echo "Copiando para /Applications/mkvis3d.app..."
        rm -rf "/Applications/mkvis3d.app"
        cp -R "$APP_TARGET" "/Applications/mkvis3d.app"
        xattr -cr "/Applications/mkvis3d.app" 2>/dev/null || true
        echo "✅ mkvis3d instalado em /Applications com sucesso!"
    fi
else
    echo "Aviso: dist/mkvis3d.app ainda não foi gerado. Rode primeiro: uv run python scripts/build_app.py"
fi

echo ""
echo "======================================================================"
echo "⚠️  Instrução importante para os usuários de Mac (Gatekeeper / Quarentena):"
echo ""
echo "Como o app ainda não possui uma assinatura paga de desenvolvedor Apple (notarização):"
echo "Quando o usuário baixar o .zip pelo navegador e descompactar o mkvis3d.app,"
echo "o macOS bloqueará a execução dizendo que \"o app não pôde ser verificado\"."
echo ""
echo "Na descrição da sua Release e no suporte ao usuário:"
echo ""
echo "No macOS (primeira execução):"
echo "• Clique com o botão direito (ou Control + clique) sobre o mkvis3d.app e escolha Abrir (Open)."
echo "• Ou rode no Terminal:"
echo "  xattr -cr mkvis3d.app"
echo "======================================================================"
echo ""
