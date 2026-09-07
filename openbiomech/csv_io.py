"""Reader for the wide per-marker CSV/.3d format used by vailá's `rec3d`
output: a `frame` column followed by `p{n}_x, p{n}_y, p{n}_z` triplets per
marker, matching by column *name* rather than position.

Column-matching pattern follows
`/home/preto/data/vaila/vaila/dlt3d.py:_point_numbers_from_columns`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .marker_trial import MarkerTrial


def _point_numbers_from_columns(columns) -> list[int]:
    """Point indices (the N in pN_x/pN_y/pN_z) present in a column list, sorted."""
    numbers: set[int] = set()
    for col in columns:
        if col.startswith("p") and "_" in col:
            parts = col.split("_")
            if len(parts) >= 2 and parts[0][1:].isdigit():
                numbers.add(int(parts[0][1:]))
    return sorted(numbers)


def read_wide_csv(path: str | Path, *, rate_hz: float = 100.0) -> MarkerTrial:
    """Load a wide `frame,p1_x,p1_y,p1_z,...` CSV (or `.3d`, same format) into a MarkerTrial.

    `rate_hz` defaults to 100.0 because the wide CSV/.3d format carries no
    sampling-rate metadata of its own; pass the true rate when known (e.g.
    from the paired `.c3d` file's header) to avoid silently assuming wrong.
    """
    if not np.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError("rate_hz must be finite and positive")
    df = pd.read_csv(path)
    point_numbers = _point_numbers_from_columns(df.columns)
    if not point_numbers:
        raise ValueError(f"{path}: no p{{n}}_x/_y/_z columns found")

    missing = [f"p{n}_{axis}" for n in point_numbers for axis in "xyz" if f"p{n}_{axis}" not in df]
    if missing:
        raise ValueError(f"missing coordinate columns: {', '.join(missing)}")
    labels = tuple(f"p{n}" for n in point_numbers)
    n_frames = len(df)
    n_markers = len(labels)
    xyz = np.full((n_frames, n_markers, 3), np.nan, dtype=np.float64)
    for i, n in enumerate(point_numbers):
        xyz[:, i, 0] = df[f"p{n}_x"].to_numpy(dtype=np.float64)
        xyz[:, i, 1] = df[f"p{n}_y"].to_numpy(dtype=np.float64)
        xyz[:, i, 2] = df[f"p{n}_z"].to_numpy(dtype=np.float64)

    residuals = np.zeros((n_frames, n_markers), dtype=np.float64)
    return MarkerTrial(labels=labels, rate_hz=rate_hz, xyz=xyz, residuals=residuals)
