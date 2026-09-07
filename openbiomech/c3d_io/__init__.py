"""C3D readers.

`read_c3d` currently delegates to `ezc3d_reader` (a thin wrapper over the
`ezc3d` library, already used in production by vailá). `legacy_binary` is a
stub for the from-scratch binary parser described in README.md §4 — that
work is scoped to the loop in `../../loops/openbiomech-python-prototype-loop.md`,
not this scaffold.
"""

from .ezc3d_reader import read_c3d

__all__ = ["read_c3d"]
