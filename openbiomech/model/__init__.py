"""Segmental model, landmarks, ISB joint conventions, BSP, gait events.

Corresponds to README.md's `biomech-model` crate. Scoped to Phase 3 of
`../../loops/openbiomech-python-prototype-loop.md`.

- `landmark.py` / `segment.py`: real and virtual landmark trajectories,
  and the geometry (length, longitudinal axis) two landmarks alone fix.
  Implemented.
- `isb_joints.py`: generic Grood & Suntay JCS floating-axis + joint
  angular-velocity decomposition (README.md §3.3). Implemented for
  arbitrary already-defined proximal/distal axes only — per-joint
  anatomical axis definitions (which landmarks give e_flex/e_rot for the
  knee vs. the ankle) are a separate, blocked decision (see the module
  docstring and this loop's state file).
- `events.py`: gait event detection (Zeni et al. 2008 kinematic method).
  Implemented.
- `bsp.py`: Body segment parameters, Dumas et al. 2007 (user-selected table).
  `mass_fraction` and `com_fraction_from_proximal` (longitudinal CoM only,
  derived from the Dumas table's local-frame Y-axis offset) implemented.
  NOT implemented — genuinely blocked, not guessed: the anteroposterior/
  mediolateral CoM offset components (needs a 3-axis segment coordinate
  system mkvis3d doesn't have yet) and every segment's radii of
  gyration/inertia tensor (no reliably-sourced Dumas 2007 numeric values
  could be found or verified this session — see `bsp.py`'s docstring).
  `newton_euler_step` (`../inverse_dynamics/newton_euler.py`) therefore
  still cannot be driven end-to-end from BSP alone.
"""

from .bsp import com_fraction_from_proximal, mass_fraction
from .events import detect_gait_events
from .isb_joints import decompose_joint_angular_velocity, joint_floating_axis
from .landmark import Landmark, landmark_from_trial, virtual_midpoint
from .segment import Segment

__all__ = [
    "Landmark",
    "landmark_from_trial",
    "Segment",
    "virtual_midpoint",
    "joint_floating_axis",
    "decompose_joint_angular_velocity",
    "detect_gait_events",
    "mass_fraction",
    "com_fraction_from_proximal",
]
