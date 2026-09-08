"""Package entrypoint allowing execution via `python -m openbiomech`."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
