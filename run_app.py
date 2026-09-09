"""Application entrypoint compatibility wrapper for mkvis3d.

Directs execution to mkvis3d.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from mkvis3d import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
