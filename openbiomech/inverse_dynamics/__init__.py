"""Force-plate mechanics (COP, types 1-5) and recursive Newton-Euler inverse
dynamics.

Corresponds to README.md's `inverse-dynamics` crate. Scoped to Phase 4 of
`../../loops/openbiomech-python-prototype-loop.md`. Note: the example data
in `data/` carries no analog/force channels, so this phase uses its own
synthetic, hand-computed fixtures (`../../tests/test_inverse_dynamics_*.py`)
rather than a golden-trial oracle.

- `force_plate.py`: `raw_channels_to_forces` (calibration matrix, generic
  over platform types 1-5), `correct_moment_origin`, `compute_cop`
  (README.md §3.5 steps 1-4). Implemented. Step 5 (transform to the global
  lab frame via the plate's four `CORNERS`) is NOT implemented — no
  per-plate corner geometry is available; COP is returned in local plate
  coordinates.
- `newton_euler.py`: `newton_euler_step`, a single-segment recursive
  Newton-Euler step (README.md §3.6 steps 1-2). Implemented. Multi-segment
  chain traversal (walking a `Segment` tree distal-to-proximal, and
  assembling `I_i`/`r_proximal`/`r_distal` from segment pose + BSP) is the
  caller's responsibility and is out of scope here — it needs BSP, which
  is the same blocked decision as `../model/__init__.py`'s `bsp.py`.
- `joint_power.py`: `joint_power`,
  `P_joint = M_joint . (omega_distal - omega_proximal)`
  (README.md §3.6 step 3). Implemented.
"""

from .force_plate import compute_cop, correct_moment_origin, raw_channels_to_forces
from .joint_power import joint_power
from .newton_euler import GRAVITY, newton_euler_step

__all__ = [
    "raw_channels_to_forces",
    "correct_moment_origin",
    "compute_cop",
    "newton_euler_step",
    "GRAVITY",
    "joint_power",
]
