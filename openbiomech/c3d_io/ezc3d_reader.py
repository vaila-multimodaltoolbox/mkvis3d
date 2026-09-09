"""Thin wrapper over `ezc3d` for reading C3D marker trajectories.

Adapted from `/home/preto/data/vaila/vaila/readc3d_export.py:importc3d` and
`c3d_markers_to_dataframe`, stripped of the CLI/Tk-facing prints and returned
as a plain `MarkerTrial` instead of a labeled DataFrame.

This is *not* the from-scratch binary C3D parser described in README.md §4
— it is deliberately kept as a dependency on the well-tested `ezc3d` library
during the Python-prototype phase, and doubles as the numerical oracle that
a future custom parser (`legacy_binary.py`) will be validated against.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from ezc3d import c3d

from ..marker_trial import MarkerTrial


def _point_labels(point_params: dict) -> list[str]:
    """Concatenate LABELS, LABELS2, LABELS3, ... groups (ezc3d's convention
    for marker sets exceeding one parameter block).
    """
    labels = list(point_params.get("LABELS", {}).get("value", []))
    suffix = 2
    while f"LABELS{suffix}" in point_params:
        labels.extend(point_params[f"LABELS{suffix}"]["value"])
        suffix += 1
    return labels


def read_c3d(path: str | Path) -> MarkerTrial:
    """Read marker trajectories (and reconstruction residuals) from a C3D file."""
    datac3d = c3d(str(path), extract_forceplat_data=True)

    marker_labels = _point_labels(datac3d["parameters"]["POINT"])
    marker_freq = float(datac3d["header"]["points"]["frame_rate"])

    point_data = datac3d["data"]["points"]  # (4, n_markers, n_frames): X,Y,Z,1
    residuals = datac3d["data"]["meta_points"]["residuals"]  # (1, n_markers, n_frames)
    analog_data = datac3d["data"]["analogs"]
    analog_labels = tuple(datac3d["parameters"]["ANALOG"]["LABELS"]["value"])
    analog_units = tuple(datac3d["parameters"]["ANALOG"]["UNITS"]["value"])
    analog_rate = float(datac3d["parameters"]["ANALOG"]["RATE"]["value"][0])

    n_used = datac3d["parameters"]["POINT"]["USED"]["value"][0]
    if n_used <= 0 or not marker_labels:
        xyz = np.zeros((0, 0, 3), dtype=np.float64)
        res = np.zeros((0, 0), dtype=np.float64)
        return MarkerTrial(labels=(), rate_hz=marker_freq, xyz=xyz, residuals=res)

    # (4, n_markers, n_frames) -> (n_frames, n_markers, 3)
    xyz = point_data[0:3, :, :].transpose(2, 1, 0).astype(np.float64)
    # (1, n_markers, n_frames) -> (n_frames, n_markers)
    res = residuals[0, :, :].T.astype(np.float64)
    n_frames = xyz.shape[0]
    n_channels = analog_data.shape[1]
    n_subsamples = analog_data.shape[2] // n_frames if n_frames and n_channels else 0
    analog = (
        analog_data[0].T.reshape(n_frames, n_subsamples, n_channels).astype(np.float64)
        if n_subsamples
        else np.zeros((n_frames, 0, 0), dtype=np.float64)
    )

    return MarkerTrial(
        labels=tuple(marker_labels),
        rate_hz=marker_freq,
        xyz=xyz,
        residuals=res,
        analog_labels=analog_labels,
        analog_units=analog_units,
        analog_rate_hz=analog_rate,
        analog=analog,
    )
