"""Application entrypoint for mkvis3d standalone binary and desktop launchers."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from openbiomech.cli import main  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = ["gui"]
    sys.exit(main(args))
