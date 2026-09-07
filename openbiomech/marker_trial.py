"""Shared in-memory representation for a marker trajectory trial.

Both `csv_io.read_wide_csv` and `c3d_io.read_c3d` return this dataclass so
callers (and tests) can compare trials loaded from different file formats
without caring which reader produced them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MarkerTrial:
    """A single motion-capture trial's marker trajectories.

    Attributes:
        labels: marker names, e.g. ("p1", "p2", ..., "p70").
        rate_hz: point sampling frequency in Hz.
        xyz: (n_frames, n_markers, 3) float64 array, meters. NaN marks a
            missing/occluded sample for that marker at that frame.
        residuals: (n_frames, n_markers) float64 array of C3D-style
            reconstruction residuals; NaN or 0.0 when the source format
            (e.g. plain CSV) does not carry residual information.
    """

    labels: tuple[str, ...]
    rate_hz: float
    xyz: np.ndarray
    residuals: np.ndarray

    @property
    def n_frames(self) -> int:
        return self.xyz.shape[0]

    @property
    def n_markers(self) -> int:
        return self.xyz.shape[1]

    def marker(self, label: str) -> np.ndarray:
        """Return the (n_frames, 3) trajectory for one marker label."""
        idx = self.labels.index(label)
        return self.xyz[:, idx, :]
