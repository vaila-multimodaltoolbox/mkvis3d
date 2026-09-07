"""Grood & Suntay / ISB joint coordinate system (JCS) decomposition
(README.md's `isb_joints.rs`, formulas in README.md §3.3).

Scope: this module implements only the *generic* JCS math README.md §3.3
actually gives a closed formula for — given a proximal fixed axis
`e_flex` and a distal fixed axis `e_rot` (already expressed as unit
vectors in a common global frame, one per frame), it builds the floating
axis and decomposes a joint angular-velocity vector onto the resulting
(generally non-orthogonal) `{e_flex, e_float, e_rot}` basis.

What is deliberately NOT done here: choosing which anatomical landmarks
define `e_flex`/`e_rot` for a specific joint (e.g. femoral epicondyles for
the knee flexion axis, malleoli for the ankle). That is a per-joint ISB
convention with published variants and, per
`../../loops/openbiomech-python-prototype-loop.md`'s Terminal States
("blocked"), is not something this loop guesses — it needs a human
decision plus anatomically-labelled markers (the golden fixture only has
generic `p1..p70` labels, not e.g. `LFEP`/`RANK`), neither of which exist
yet. `segment.py` already documents the same deferral for the third
JCS-defining landmark.
"""

from __future__ import annotations

import numpy as np


def joint_floating_axis(e_flex: np.ndarray, e_rot: np.ndarray) -> np.ndarray:
    """Per-frame floating axis `e_float`, perpendicular to both fixed axes.

    README.md §3.3: `e_float = (e_flex x e_rot) / |e_flex x e_rot|`.

    Args:
        e_flex: `(..., 3)` proximal fixed axis (`e_1`), unit vectors.
        e_rot: `(..., 3)` distal fixed axis (`f_3`), unit vectors.

    Returns:
        `(..., 3)` unit vectors. NaN where `e_flex` and `e_rot` are
        (anti)parallel — the floating axis is undefined there (gimbal-lock
        analogue of the JCS itself), never silently a zero vector.

    Raises:
        ValueError: if `e_flex`/`e_rot` have mismatched shapes.
    """
    flex = np.asarray(e_flex, dtype=np.float64)
    rot = np.asarray(e_rot, dtype=np.float64)
    if flex.shape != rot.shape:
        raise ValueError(f"e_flex/e_rot shape mismatch: {flex.shape} vs {rot.shape}")
    if flex.shape[-1] != 3:
        raise ValueError(f"expected (..., 3) axis vectors, got {flex.shape}")

    cross = np.cross(flex, rot)
    norm = np.linalg.norm(cross, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        e_float = cross / norm[..., np.newaxis]
    e_float[norm == 0.0] = np.nan
    return e_float


def decompose_joint_angular_velocity(
    omega_joint: np.ndarray,
    e_flex: np.ndarray,
    e_float: np.ndarray,
    e_rot: np.ndarray,
) -> np.ndarray:
    """Decompose a relative joint angular velocity onto the JCS basis.

    README.md §3.3: `omega_joint = alpha_dot*e_flex + beta_dot*e_float +
    gamma_dot*e_rot`. The three axes are unit vectors but generally *not*
    orthogonal to each other, so recovering `(alpha_dot, beta_dot,
    gamma_dot)` from a given `omega_joint` is a per-frame 3x3 linear solve
    against the basis matrix `[e_flex, e_float, e_rot]`, not a dot product.

    Args:
        omega_joint: `(..., 3)` relative angular velocity of the distal
            segment w.r.t. the proximal one, expressed in the global frame.
        e_flex, e_float, e_rot: `(..., 3)` unit basis vectors, same shape
            as `omega_joint` (see `joint_floating_axis` for `e_float`).

    Returns:
        `(..., 3)` array of `(alpha_dot, beta_dot, gamma_dot)`, same units
        as `omega_joint` (radians/s). NaN where the basis is degenerate
        (singular, e.g. `e_flex` parallel to `e_rot`) rather than a bogus
        solve.

    Raises:
        ValueError: on mismatched input shapes.
    """
    omega = np.asarray(omega_joint, dtype=np.float64)
    flex = np.asarray(e_flex, dtype=np.float64)
    float_ax = np.asarray(e_float, dtype=np.float64)
    rot = np.asarray(e_rot, dtype=np.float64)
    shapes = {omega.shape, flex.shape, float_ax.shape, rot.shape}
    if len(shapes) != 1:
        raise ValueError(f"omega_joint/e_flex/e_float/e_rot shape mismatch: {shapes}")
    if omega.shape[-1] != 3:
        raise ValueError(f"expected (..., 3) vectors, got {omega.shape}")

    batch_shape = omega.shape[:-1]
    omega_flat = omega.reshape(-1, 3)
    # Columns are the basis vectors: solving basis @ coeffs = omega_joint
    # for coeffs is exactly the non-orthogonal decomposition.
    basis = np.stack(
        [flex.reshape(-1, 3), float_ax.reshape(-1, 3), rot.reshape(-1, 3)], axis=-1
    )  # (n, 3, 3), columns = e_flex, e_float, e_rot

    coeffs = np.full_like(omega_flat, np.nan)
    with np.errstate(invalid="ignore"):
        dets = np.linalg.det(basis)
    solvable = np.abs(dets) > 1e-9
    if np.any(solvable):
        # Trailing singleton axis makes the batch-of-vectors shape (k, 3, 1)
        # unambiguous for np.linalg.solve regardless of how it dispatches
        # between the vector (b.ndim == a.ndim - 1) and matrix batch forms.
        rhs = omega_flat[solvable][..., np.newaxis]
        coeffs[solvable] = np.linalg.solve(basis[solvable], rhs)[..., 0]
    return coeffs.reshape(*batch_shape, 3)
