"""C3D readers.

`read_c3d` delegates to `ezc3d_reader` (a thin wrapper over the `ezc3d`
library, already used in production by vailá) and serves as the numerical
oracle. `read_c3d_native` is the from-scratch binary parser described in
README.md §4 (Phase 1 of `../../loops/openbiomech-python-prototype-loop.md`);
the two are asserted to agree on the golden fixture in
`tests/test_c3d_io_native.py`.
"""

from .ezc3d_reader import read_c3d
from .legacy_binary import AnalogData, C3DFile, PointData, read_c3d_file
from .legacy_binary import read_c3d as read_c3d_native

__all__ = [
    "AnalogData",
    "C3DFile",
    "PointData",
    "read_c3d",
    "read_c3d_file",
    "read_c3d_native",
]
