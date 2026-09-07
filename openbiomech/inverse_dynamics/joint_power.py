"""Joint power (README.md's `joint_power.rs`, formula in README.md §3.6 step 3)."""

from __future__ import annotations

import numpy as np


def joint_power(
    joint_moment: np.ndarray, omega_distal: np.ndarray, omega_proximal: np.ndarray
) -> np.ndarray:
    """`P_joint = M_joint . (w_distal - w_proximal)` (README.md §3.6.3).

    Args:
        joint_moment: `(..., 3)` joint moment (typically the proximal
            segment's `moment_proximal` from `newton_euler_step`, expressed
            at the joint).
        omega_distal: `(..., 3)` distal segment angular velocity, global
            frame.
        omega_proximal: `(..., 3)` proximal segment angular velocity,
            global frame, same leading shape.

    Returns:
        `(...,)` scalar joint power (W).

    Raises:
        ValueError: mismatched shapes.
    """
    m = np.asarray(joint_moment, dtype=np.float64)
    wd = np.asarray(omega_distal, dtype=np.float64)
    wp = np.asarray(omega_proximal, dtype=np.float64)
    if not (m.shape == wd.shape == wp.shape):
        raise ValueError(
            f"shape mismatch: joint_moment {m.shape}, omega_distal {wd.shape}, "
            f"omega_proximal {wp.shape}"
        )
    if m.shape[-1] != 3:
        raise ValueError(f"expected (..., 3) vectors, got {m.shape}")

    return np.sum(m * (wd - wp), axis=-1)
