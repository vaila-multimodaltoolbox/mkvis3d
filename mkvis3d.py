#!/usr/bin/env python3
"""mkvis3d — OpenBiomech motion viewer and reproducible biomechanics.

Main application entrypoint.
Can be executed directly from terminal, script, or double-clicked:
    ./mkvis3d.py
    python mkvis3d.py
    ./mkvis3d.py data/rec3d_20260826_121305_m.c3d
    ./mkvis3d.py view trial.c3d --output viewer.html
    ./mkvis3d.py lcs trial.c3d --ap +Z --axial +Y --output transformed.c3d
    ./mkvis3d.py filter trial.c3d --cutoff 6.0 --interp linear --output filtered.c3d
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

# Self-bootstrap into .venv if system python was invoked directly
venv_python = (
    root / ".venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else root / ".venv" / "bin" / "python"
)
if venv_python.exists() and sys.executable != str(venv_python.resolve()):
    try:
        import scipy  # noqa: F401
    except ImportError:
        os.execv(str(venv_python), [str(venv_python), *sys.argv])

from openbiomech.cli import main  # noqa: E402


def run(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]

    # Default behavior: if no arguments or double-clicked, launch GUI
    if not args:
        return main(["gui"])

    # If the first argument is an existing motion file (c3d, csv, 3d), open GUI with it
    first_arg = args[0]
    known_commands = {
        "info",
        "segment",
        "view",
        "gui",
        "blender",
        "bvh",
        "demo",
        "dynamics",
        "lcs",
        "filter",
        "install",
    }
    if (
        not first_arg.startswith("-")
        and first_arg not in known_commands
        and Path(first_arg).suffix.lower() in {".c3d", ".csv", ".3d"}
    ):
        return main(["gui", *args])

    return main(args)


if __name__ == "__main__":
    sys.exit(run())
