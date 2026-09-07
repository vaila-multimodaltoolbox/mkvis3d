"""Rigid segment definition — geometry only (README.md's `segment.rs`).

Scoped to what two landmarks alone determine: per-frame length and the
longitudinal axis (README.md §3.1 point 2's Z axis, "directed proximally").
A full anatomical coordinate system needs a third, joint-specific reference
landmark to fix the in-plane X/Y axes (Grood & Suntay / ISB, README.md
§3.3), and mass/CoM/inertia need a body-segment-parameter table — both are
separate, later items in phase 3 of
`../../loops/openbiomech-python-prototype-loop.md` and deliberately not
guessed at here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .landmark import Landmark


@dataclass
class Segment:
    """A rigid segment spanned by a proximal and a distal landmark.

    Attributes:
        name: segment name, e.g. "thigh_r".
        proximal: proximal-end landmark.
        distal: distal-end landmark.
    """

    name: str
    proximal: Landmark
    distal: Landmark

    def __post_init__(self) -> None:
        if self.proximal.positions.shape != self.distal.positions.shape:
            raise ValueError(
                f"segment {self.name!r}: proximal landmark {self.proximal.name!r} "
                f"is {self.proximal.positions.shape}, distal landmark "
                f"{self.distal.name!r} is {self.distal.positions.shape}"
            )

    @property
    def n_frames(self) -> int:
        return self.proximal.n_frames

    def length(self) -> np.ndarray:
        """Per-frame Euclidean distance between the proximal and distal
        landmarks. NaN where either landmark is occluded that frame.
        """
        return np.linalg.norm(self.proximal.positions - self.distal.positions, axis=1)

    def longitudinal_axis(self) -> np.ndarray:
        """Per-frame unit vector along the segment, distal -> proximal.

        Matches README.md §3.1 point 2: "Z: Longitudinal / Superior axis
        directed proximally." NaN where either landmark is occluded, or the
        two landmarks coincide that frame (zero length, direction
        undefined) — never inf/NaN silently propagated as a bogus unit
        vector.
        """
        vec = self.proximal.positions - self.distal.positions
        length = np.linalg.norm(vec, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            axis = vec / length[:, np.newaxis]
        undefined = ~(length > 0.0)  # covers both 0.0 and NaN
        axis[undefined] = np.nan
        return axis
