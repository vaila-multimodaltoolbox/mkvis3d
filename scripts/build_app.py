#!/usr/bin/env python3
"""Cross-platform build script for mkvis3d executable."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    system = platform.system().lower()
    print(f"=== Building mkvis3d for {platform.system()} ({platform.machine()}) ===")

    spec_file = root / "mkvis3d.spec"
    if not spec_file.exists():
        print(f"Error: Spec file not found at {spec_file}", file=sys.stderr)
        return 1

    cmd = [
        "uv",
        "run",
        "--with",
        "pyinstaller",
        "pyinstaller",
        "--clean",
        "-y",
        str(spec_file),
    ]

    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(root))
    if res.returncode != 0:
        print("Build failed.", file=sys.stderr)
        return res.returncode

    dist_dir = root / "dist"
    print("\n=== Build Completed Successfully! ===")
    if system == "windows":
        exe_path = dist_dir / "mkvis3d.exe"
        print(f"Windows Executable: {exe_path}")
        release_path = dist_dir / "mkvis3d-windows-x86_64.exe"
        if exe_path.exists():
            shutil.copy2(exe_path, release_path)
            print(f"Windows Release Executable: {release_path}")
    elif system == "linux":
        bin_path = dist_dir / "mkvis3d"
        print(f"Linux Executable: {bin_path}")
        release_path = dist_dir / "mkvis3d-linux-x86_64"
        if bin_path.exists():
            shutil.copy2(bin_path, release_path)
            release_path.chmod(0o755)
            print(f"Linux Release Executable: {release_path}")
    elif system == "darwin":
        app_path = dist_dir / "mkvis3d.app"
        print(f"macOS Application: {app_path}")
        zip_path = dist_dir / "mkvis3d-macos-app.zip"
        if app_path.exists():
            subprocess.run(
                ["zip", "-r", "-q", "mkvis3d-macos-app.zip", "mkvis3d.app"],
                cwd=str(dist_dir),
                check=False,
            )
            print(f"macOS Release Zip: {zip_path}")
        print("\n" + "=" * 70)
        print("⚠️  Instrução importante para os usuários de Mac (Gatekeeper / Quarentena):")
        print(
            "Como o app ainda não possui uma assinatura paga de desenvolvedor Apple (notarização):"
        )
        print("Quando o usuário baixar o .zip pelo navegador e descompactar o mkvis3d.app,")
        print('o macOS bloqueará a execução dizendo que "o app não pôde ser verificado".\n')
        print("Na descrição da sua Release e para usuários, adicione a instrução:")
        print("  No macOS (primeira execução):")
        print(
            "  • Clique com o botão direito (ou Control + clique) sobre o mkvis3d.app e escolha Abrir (Open)."
        )
        print("  • Ou rode no Terminal:")
        print("    xattr -cr mkvis3d.app")
        print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
