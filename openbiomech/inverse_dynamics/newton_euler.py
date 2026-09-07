"""Recursive Newton-Euler inverse dynamics, single segment
(README.md's `newton_euler.rs`, formulas in README.md §3.6, steps 1-2).

Executed by the caller from distal to proximal segment, one call per
segment: the previous call's `force_proximal`/`moment_proximal` become
this call's `distal_force`/`distal_moment` for the next segment up the
chain. Multi-segment chain traversal (walking a `Segment` tree) is out of
scope here — this module is the single-segment step formula only.

`I_i` (the instantaneous global-frame inertia tensor,
`I_i = R_i @ I_local @ R_i.T`) and the two lever arms `r_proximal`,
`r_distal` are the caller's responsibility to assemble from segment pose
and BSP data — both need BSP (mass, `I_local`, COM location), which is a
separate blocked decision (see `../model/__init__.py`). This module takes
them as already-computed inputs so the formula itself is verifiable
independent of that blocker.
"""

from __future__ import annotations

import numpy as np

GRAVITY = np.array([0.0, 0.0, -9.80665])
"""m/s^2, README.md §3.6 step 1."""


def newton_euler_step(
    mass: float,
    com_acceleration: np.ndarray,
    inertia_tensor: np.ndarray,
    angular_velocity: np.ndarray,
    angular_acceleration: np.ndarray,
    distal_force: np.ndarray,
    distal_moment: np.ndarray,
    r_proximal: np.ndarray,
    r_distal: np.ndarray,
) -> dict[str, np.ndarray]:
    """One recursive Newton-Euler step for a single segment.

    README.md §3.6:
        `F_proximal = m*(a_com - g) - F_distal`
        `M_proximal = I*w_dot + w x (I*w) - M_distal
                       - (r_distal x F_distal) - (r_proximal x F_proximal)`

    Args:
        mass: segment mass (kg), scalar.
        com_acceleration: `(..., 3)` segment COM linear acceleration,
            global frame.
        inertia_tensor: `(..., 3, 3)` instantaneous inertia tensor in the
            global frame (`I_i = R_i @ I_local @ R_i.T`, assembled by the
            caller).
        angular_velocity: `(..., 3)` segment angular velocity, global
            frame.
        angular_acceleration: `(..., 3)` segment angular acceleration,
            global frame.
        distal_force: `(..., 3)` reaction force applied by the distal
            segment/ground on this segment (zero for the most-distal
            segment; the ground-reaction force for a foot segment, from
            `force_plate.compute_cop`'s `force`, sign per the caller's
            convention).
        distal_moment: `(..., 3)` reaction moment from the distal
            segment/ground, same convention as `distal_force`.
        r_proximal: `(..., 3)` proximal joint centre minus segment COM.
        r_distal: `(..., 3)` distal joint centre minus segment COM.

    Returns:
        `{"force_proximal": (..., 3), "moment_proximal": (..., 3)}`.

    Raises:
        ValueError: mismatched shapes.
    """
    a = np.asarray(com_acceleration, dtype=np.float64)
    inertia = np.asarray(inertia_tensor, dtype=np.float64)
    omega = np.asarray(angular_velocity, dtype=np.float64)
    omega_dot = np.asarray(angular_acceleration, dtype=np.float64)
    f_distal = np.asarray(distal_force, dtype=np.float64)
    m_distal = np.asarray(distal_moment, dtype=np.float64)
    r_prox = np.asarray(r_proximal, dtype=np.float64)
    r_dist = np.asarray(r_distal, dtype=np.float64)

    vectors = {
        "com_acceleration": a,
        "angular_velocity": omega,
        "angular_acceleration": omega_dot,
        "distal_force": f_distal,
        "distal_moment": m_distal,
        "r_proximal": r_prox,
        "r_distal": r_dist,
    }
    shape = a.shape
    for name, v in vectors.items():
        if v.shape != shape:
            raise ValueError(f"shape mismatch: com_acceleration is {shape}, {name} is {v.shape}")
    if inertia.shape != shape + (3,):
        raise ValueError(f"expected inertia_tensor shape {shape + (3,)}, got {inertia.shape}")

    force_proximal = mass * (a - GRAVITY) - f_distal

    i_omega_dot = np.squeeze(inertia @ omega_dot[..., np.newaxis], axis=-1)
    i_omega = np.squeeze(inertia @ omega[..., np.newaxis], axis=-1)
    gyroscopic = np.cross(omega, i_omega)
    r_distal_cross_f = np.cross(r_dist, f_distal)
    r_proximal_cross_f = np.cross(r_prox, force_proximal)

    moment_proximal = i_omega_dot + gyroscopic - m_distal - r_distal_cross_f - r_proximal_cross_f

    return {"force_proximal": force_proximal, "moment_proximal": moment_proximal}
