#!/usr/bin/env python3
"""Cross-platform build script for mkvis3d executable."""

import platform
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
    elif system == "darwin":
        app_path = dist_dir / "mkvis3d.app"
        print(f"macOS Application: {app_path}")
    else:
        bin_path = dist_dir / "mkvis3d"
        print(f"Linux Executable: {bin_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
