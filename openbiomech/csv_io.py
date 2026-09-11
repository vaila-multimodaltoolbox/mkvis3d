"""Reader and writer for wide per-marker CSV/.3d formats.

Supports:
- Legacy vailá `rec3d` numbered marker convention: `frame, p1_x, p1_y, p1_z, ...`
- Generic named marker conventions: `frame, nose_x, nose_y, nose_z, ...`
- Diverse separators: underscore (`_`), dot (`.`), colon (`:`), space (` `),
  dash (`-`), slash (`/`), or bracketed coordinate notations like `Marker[X]`.
- Delimiter autodetection (comma, semicolon, tab, whitespace).
- Multi-line header CSVs with separate marker and coordinate rows.
- Automatic sampling rate inference when a consistent `time` column is present.
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from .marker_trial import MarkerTrial


def _point_numbers_from_columns(columns: Sequence[str]) -> list[int]:
    """Point indices (the N in pN_x/pN_y/pN_z) present in a column list, sorted."""
    numbers: set[int] = set()
    for col in columns:
        col_str = str(col).strip()
        if col_str.startswith("p") and "_" in col_str:
            parts = col_str.split("_")
            if len(parts) >= 2 and parts[0][1:].isdigit():
                numbers.add(int(parts[0][1:]))
    return sorted(numbers)


def _parse_column_axis(col: str) -> tuple[str, str] | None:
    """Extract (marker_name, axis) from a column header string."""
    col_str = str(col).strip()
    if not col_str:
        return None

    # 1. Bracket syntax: marker[x], marker(x), marker [X]
    m = re.match(r"^(.*?)\s*[\[\(]([xyzXYZ])[\]\)]\s*$", col_str)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2).lower()

    # 2. Separator syntax: marker_x, marker.x, marker:x, marker x, marker-x, marker/x
    m = re.match(r"^(.*)[_.:\s/-]([xyzXYZ])$", col_str)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2).lower()

    # 3. Standalone axis: x, y, z
    if col_str.lower() in ("x", "y", "z"):
        return "p1", col_str.lower()

    # 4. Trailing axis letter without separator: markerX, markerY, markerZ
    m = re.match(r"^(.*?)([xyzXYZ])$", col_str)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2).lower()

    return None


def _extract_marker_columns(
    columns: Sequence[str],
) -> tuple[list[str], dict[str, dict[str, str]], dict[str, str]]:
    """Identify markers with complete (x, y, z) triplets and optional residuals."""
    res_re = re.compile(r"^(.*)[_.:\s/-](residual|res|err|error)$", re.IGNORECASE)
    marker_axes: dict[str, dict[str, str]] = {}
    marker_order: list[str] = []
    residuals_map: dict[str, str] = {}

    for col in columns:
        col_str = str(col).strip()
        if not col_str:
            continue

        m_res = res_re.match(col_str)
        if m_res and m_res.group(1).strip():
            residuals_map[m_res.group(1).strip()] = col
            continue

        parsed = _parse_column_axis(col_str)
        if parsed:
            name, axis = parsed
            if name not in marker_axes:
                marker_axes[name] = {}
                marker_order.append(name)
            marker_axes[name][axis] = col

    missing = [
        f"{name}_{axis}" for name in marker_order for axis in "xyz" if axis not in marker_axes[name]
    ]
    if missing:
        raise ValueError(f"missing coordinate columns: {', '.join(missing)}")

    valid_markers = [
        name
        for name in marker_order
        if "x" in marker_axes[name] and "y" in marker_axes[name] and "z" in marker_axes[name]
    ]

    # If every marker is p{digits}, sort numerically for 100% backward-compatibility
    if valid_markers and all(name.startswith("p") and name[1:].isdigit() for name in valid_markers):
        valid_markers.sort(key=lambda x: int(x[1:]))

    return valid_markers, marker_axes, residuals_map


def _normalize_header(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize multi-line header CSVs where row 0 has marker names and row 1 has X,Y,Z."""
    if len(df) > 0:
        first_row_vals = [str(x).strip().lower() for x in df.iloc[0] if pd.notna(x)]
        xyz_count = sum(1 for v in first_row_vals if v in ("x", "y", "z"))
        if xyz_count >= 3 and xyz_count / max(len(first_row_vals), 1) > 0.5:
            new_cols: list[str] = []
            curr_marker = ""
            for col_name, sub_val in zip(df.columns, df.iloc[0], strict=False):
                col_str = str(col_name).strip()
                sub_str = str(sub_val).strip() if pd.notna(sub_val) else ""
                if not col_str.startswith("Unnamed:") and col_str != "":
                    curr_marker = col_str
                if sub_str.lower() in ("x", "y", "z") and curr_marker:
                    new_cols.append(f"{curr_marker}_{sub_str.lower()}")
                else:
                    new_cols.append(col_str if not col_str.startswith("Unnamed:") else sub_str)
            df = df.iloc[1:].copy()
            df.columns = new_cols
            df.reset_index(drop=True, inplace=True)
    return df


def read_wide_csv(path: str | Path | io.StringIO, *, rate_hz: float = 100.0) -> MarkerTrial:
    """Load a wide CSV (or `.3d`, same format) with arbitrary marker headers into a MarkerTrial.

    Supports arbitrary marker names (e.g. `nose_x, nose_y, nose_z` or `p1_x, p1_y, p1_z`),
    various coordinate suffixes (`_x`, `.x`, `:x`, `[x]`, etc.), multiple delimiters,
    and multi-line headers.

    `rate_hz` defaults to 100.0 because wide CSV formats carry no standardized
    sampling-rate metadata; if a monotonic `time` column is found, the rate is
    automatically computed if `rate_hz` is left at default.
    """
    if not np.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError("rate_hz must be finite and positive")

    try:
        df = pd.read_csv(path, comment="#")
        if len(df.columns) <= 1:
            if isinstance(path, io.StringIO):
                path.seek(0)
            df = pd.read_csv(path, sep=None, engine="python", comment="#")
    except Exception:
        if isinstance(path, io.StringIO):
            path.seek(0)
        df = pd.read_csv(path, sep=None, engine="python", comment="#")

    df = _normalize_header(df)

    valid_markers, marker_axes, residuals_map = _extract_marker_columns(df.columns)
    if not valid_markers:
        raise ValueError(f"{path}: no 3D marker coordinate triplets (x, y, z) found in columns")

    # Inferred sampling rate if monotonic time column exists and rate_hz is default 100.0
    if rate_hz == 100.0:
        for t_col in df.columns:
            if str(t_col).strip().lower() in ("time", "timestamp", "t"):
                try:
                    times = (
                        pd.to_numeric(df[t_col], errors="coerce")
                        .dropna()
                        .to_numpy(dtype=np.float64)
                    )
                    if len(times) >= 2:
                        dts = np.diff(times)
                        valid_dts = dts[dts > 0]
                        if len(valid_dts) > 0:
                            mean_dt = float(np.mean(valid_dts))
                            if 1e-4 <= mean_dt <= 10.0:
                                rate_hz = round(1.0 / mean_dt, 4)
                                break
                except Exception:
                    pass

    labels = tuple(valid_markers)
    n_frames = len(df)
    n_markers = len(labels)
    xyz = np.full((n_frames, n_markers, 3), np.nan, dtype=np.float64)
    residuals = np.zeros((n_frames, n_markers), dtype=np.float64)

    for i, marker in enumerate(valid_markers):
        cols = marker_axes[marker]
        xyz[:, i, 0] = pd.to_numeric(df[cols["x"]], errors="coerce").to_numpy(dtype=np.float64)
        xyz[:, i, 1] = pd.to_numeric(df[cols["y"]], errors="coerce").to_numpy(dtype=np.float64)
        xyz[:, i, 2] = pd.to_numeric(df[cols["z"]], errors="coerce").to_numpy(dtype=np.float64)

        if marker in residuals_map:
            residuals[:, i] = pd.to_numeric(df[residuals_map[marker]], errors="coerce").to_numpy(
                dtype=np.float64
            )

    return MarkerTrial(labels=labels, rate_hz=rate_hz, xyz=xyz, residuals=residuals)


def write_wide_csv(trial: MarkerTrial, path: str | Path) -> None:
    """Export MarkerTrial to wide CSV format (frame, p1_x, p1_y, p1_z, ...)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n_frames = trial.n_frames
    cols: dict[str, np.ndarray] = {"frame": np.arange(1, n_frames + 1, dtype=int)}
    for i, label in enumerate(trial.labels):
        cols[f"{label}_x"] = trial.xyz[:, i, 0]
        cols[f"{label}_y"] = trial.xyz[:, i, 1]
        cols[f"{label}_z"] = trial.xyz[:, i, 2]
    df = pd.DataFrame(cols)
    df.to_csv(p, index=False)
