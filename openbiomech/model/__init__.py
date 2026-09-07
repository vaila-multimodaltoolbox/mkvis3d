"""Segmental model, landmarks, ISB joint conventions, BSP, gait events.

Corresponds to README.md's `biomech-model` crate. Scoped to Phase 3 of
`../../loops/openbiomech-python-prototype-loop.md`.

- `landmark.py` / `segment.py`: real and virtual landmark trajectories,
  and the geometry (length, longitudinal axis) two landmarks alone fix.
  Implemented.
- ISB joint coordinate systems, body segment parameters (BSP), and gait
  event detection: not started.
"""

from .landmark import Landmark, landmark_from_trial, virtual_midpoint
from .segment import Segment

__all__ = [
    "Landmark",
    "landmark_from_trial",
    "Segment",
    "virtual_midpoint",
]
