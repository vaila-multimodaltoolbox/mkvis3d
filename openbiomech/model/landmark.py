"""Static/dynamic calibration landmarks & virtual targets (README.md's
`landmark.rs`).

A `Landmark` is a named 3D trajectory: either "real" (taken unmodified from
one `MarkerTrial` marker label) or "virtual" (computed from other landmarks,
e.g. a joint-centre target with no marker directly on it). Both share the
same shape so downstream code (`segment.py` and later the JCS/BSP modules)
never needs to know which kind it got.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..marker_trial import MarkerTrial


@dataclass
class Landmark:
    """A named `(n_frames, 3)` point trajectory, meters, NaN = occluded.

    Attributes:
        name: landmark label, e.g. a marker name or a virtual target name
            such as "hip_joint_centre".
        positions: `(n_frames, 3)` float64 array.
        virtual: True when `positions` was computed from other landmarks
            rather than read directly from a `MarkerTrial` marker.
    """

    name: str
    positions: np.ndarray
    virtual: bool = False

    @property
    def n_frames(self) -> int:
        return self.positions.shape[0]


def landmark_from_trial(trial: MarkerTrial, label: str, *, name: str | None = None) -> Landmark:
    """Real landmark: one `MarkerTrial` marker trajectory, unmodified.

    Args:
        trial: source trial (as returned by `c3d_io.read_c3d`/`read_c3d_native`
            or `csv_io.read_wide_csv`).
        label: marker label to look up, e.g. "p1".
        name: landmark name; defaults to `label`.
    """
    return Landmark(
        name=name or label, positions=np.array(trial.marker(label), dtype=np.float64), virtual=False
    )


def virtual_midpoint(a: Landmark, b: Landmark, name: str) -> Landmark:
    """Virtual landmark at the per-frame midpoint of two others.

    Used when no single marker sits on the point of interest (e.g. a
    mid-ASIS or mid-malleoli target). NaN (occluded) propagates: a frame
    where either input is missing yields NaN in the result rather than
    silently falling back to the other side.
    """
    if a.positions.shape != b.positions.shape:
        raise ValueError(
            f"landmark shapes must match: {a.name} is {a.positions.shape}, "
            f"{b.name} is {b.positions.shape}"
        )
    return Landmark(name=name, positions=(a.positions + b.positions) / 2.0, virtual=True)
