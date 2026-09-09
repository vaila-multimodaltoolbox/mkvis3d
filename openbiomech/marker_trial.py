"""Shared in-memory representation for a marker trajectory trial.

Both `csv_io.read_wide_csv` and `c3d_io.read_c3d` return this dataclass so
callers (and tests) can compare trials loaded from different file formats
without caring which reader produced them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ForcePlatform:
    """Calibrated physical force platform and its ground reaction wrenches.

    Attributes:
        id: 0-based platform index.
        name: platform label, e.g. "FP1".
        plate_type: C3D force platform type (e.g. 2 for Bertec/AMTI 6-component).
        corners: (4, 3) float64 array of corner coordinates in meters (global frame).
        origin: (3,) float64 array of origin offset in meters.
        channels: 0-based analog channel indices assigned to this platform.
        cop: (n_frames, 3) float64 array of Center of Pressure in meters (global frame).
        force: (n_frames, 3) float64 array of Ground Reaction Force in Newtons (global frame).
        moment: (n_frames, 3) float64 array of free moment in N*m (global frame).
        contact: (n_frames,) boolean array indicating active foot contact (|Fz| >= threshold).
    """

    id: int
    name: str
    plate_type: int
    corners: np.ndarray
    origin: np.ndarray
    channels: tuple[int, ...]
    cop: np.ndarray
    force: np.ndarray
    moment: np.ndarray
    contact: np.ndarray


@dataclass
class MarkerTrial:
    """A single motion-capture trial's marker trajectories and force platforms.

    Attributes:
        labels: marker names, e.g. ("p1", "p2", ..., "p70").
        rate_hz: point sampling frequency in Hz.
        xyz: (n_frames, n_markers, 3) float64 array, meters. NaN marks a
            missing/occluded sample for that marker at that frame.
        residuals: (n_frames, n_markers) float64 array of C3D-style
            reconstruction residuals; NaN or 0.0 when the source format
            (e.g. plain CSV) does not carry residual information.
        force_plates: optional list of calibrated ForcePlatform objects.
        analog_labels: optional tuple of analog channel names.
        analog_units: optional tuple of physical units for analog channels.
        analog_rate_hz: optional analog sampling frequency in Hz.
        analog: optional `(n_frames, n_subsamples, n_channels)` float64
            calibrated analog samples synchronized to point frames.
    """

    labels: tuple[str, ...]
    rate_hz: float
    xyz: np.ndarray
    residuals: np.ndarray
    force_plates: list[ForcePlatform] = field(default_factory=list)
    analog_labels: tuple[str, ...] = ()
    analog_units: tuple[str, ...] = ()
    analog_rate_hz: float = 0.0
    analog: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 0, 0), dtype=np.float64)
    )

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
