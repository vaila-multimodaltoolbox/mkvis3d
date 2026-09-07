"""Shared loading policy for CLI and viewer; all output coordinates in metres."""

from pathlib import Path

from .c3d_io import read_c3d_native
from .csv_io import read_wide_csv
from .marker_trial import MarkerTrial


def load_trial(path: str | Path, *, rate_hz: float = 100.0, units: str = "m") -> MarkerTrial:
    path = Path(path)
    if path.suffix.lower() == ".c3d":
        return read_c3d_native(path)
    if path.suffix.lower() in (".csv", ".3d"):
        if units not in ("m", "cm", "mm"):
            raise ValueError("CSV units must be m, cm or mm")
        trial = read_wide_csv(path, rate_hz=rate_hz)
        trial.xyz *= {"m": 1.0, "cm": 0.01, "mm": 0.001}[units]
        return trial
    raise ValueError(
        f"{path}: unrecognized extension {path.suffix!r} (expected .c3d, .csv, or .3d)"
    )
