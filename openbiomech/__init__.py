"""OpenBiomech — open-source Visual3D/Mokka alternative (Python prototype phase).

See CLAUDE.md for current phase and README.md for the long-term Rust
architecture this package is prototyping.
"""

from importlib.metadata import PackageNotFoundError, version

from . import biomech_math, c3d_io, csv_io

try:
    __version__ = version("openbiomech")
except PackageNotFoundError:  # editable/source tree without installed metadata
    __version__ = "0.0.1"

__all__ = ["__version__", "biomech_math", "c3d_io", "csv_io"]
