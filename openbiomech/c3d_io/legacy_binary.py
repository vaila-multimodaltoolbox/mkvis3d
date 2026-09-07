"""From-scratch C3D binary parser (README.md §4: 512-byte header blocks,
DEC VAX / Intel / MIPS processor flags, parameter groups, SoA data layout).

Not implemented yet — scoped to Phase 1 of
`../../loops/openbiomech-python-prototype-loop.md`. When implemented, its
output must match `ezc3d_reader.read_c3d` within the golden-fixture
tolerance asserted in `tests/test_c3d_io_golden.py` before this stub is
considered done.
"""

from __future__ import annotations

from pathlib import Path

from ..marker_trial import MarkerTrial


def read_c3d(path: str | Path) -> MarkerTrial:
    raise NotImplementedError(
        "Custom binary C3D parser not implemented yet — see README.md §4 and "
        "loops/openbiomech-python-prototype-loop.md Phase 1. "
        "Use openbiomech.c3d_io.ezc3d_reader.read_c3d for now."
    )
