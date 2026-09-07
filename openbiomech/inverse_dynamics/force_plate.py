"""Force-plate mechanics: raw-channel calibration and centre of pressure
(README.md's `force_plate.rs` + `cop.rs`, formulas in README.md §3.5).

Scope: README.md §3.5 gives a full closed formula for turning calibrated
`(Fx, Fy, Fz, Mx, My, Mz)` into a corrected COP (steps 2-4 below); step 1
(raw voltage -> force/moment via a `6x6` calibration matrix) is the same
linear-algebra step for every platform type (1-5) — they differ only in
*what that matrix and the channel wiring are*, which is hardware-specific
setup data this repo does not have. Step 5 (transform to the global lab
frame via the plate's four `CORNERS`) needs that per-plate corner geometry
and is not implemented yet — COP here is returned in local plate
coordinates, matching the README formula exactly.
"""

from __future__ import annotations

import numpy as np


def raw_channels_to_forces(voltages: np.ndarray, calibration_matrix: np.ndarray) -> np.ndarray:
    """Step 1: `F_raw = C @ V_analog` (README.md §3.5.1).

    Args:
        voltages: `(..., 6)` raw analog channel samples.
        calibration_matrix: `(6, 6)` plate calibration matrix `C`, mapping
            raw channels to `(Fx, Fy, Fz, Mx, My, Mz)`. The matrix's
            content (not this function) is what differs between platform
            types 1-5.

    Returns:
        `(..., 6)` `(Fx, Fy, Fz, Mx, My, Mz)`.

    Raises:
        ValueError: wrong trailing shape on either input.
    """
    v = np.asarray(voltages, dtype=np.float64)
    c = np.asarray(calibration_matrix, dtype=np.float64)
    if v.shape[-1] != 6:
        raise ValueError(f"expected (..., 6) voltage channels, got {v.shape}")
    if c.shape != (6, 6):
        raise ValueError(f"expected a (6, 6) calibration matrix, got {c.shape}")
    return v @ c.T


def correct_moment_origin(force: np.ndarray, moment: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """Step 2: correct `(Mx, My)` for the sensor's geometric origin offset.

    README.md §3.5.2:
        `Mx' = Mx + Fy*z0 - Fz*y0`
        `My' = My - Fx*z0 + Fz*x0`
    `Mz` is unaffected (the free moment about the vertical axis).

    Args:
        force: `(..., 3)` `(Fx, Fy, Fz)`.
        moment: `(..., 3)` `(Mx, My, Mz)`, same leading shape as `force`.
        origin: `(3,)` `(x0, y0, z0)`, the plate's geometric-centre-to-
            top-surface offset.

    Returns:
        `(..., 3)` corrected `(Mx', My', Mz)`.

    Raises:
        ValueError: mismatched shapes.
    """
    f = np.asarray(force, dtype=np.float64)
    m = np.asarray(moment, dtype=np.float64)
    o = np.asarray(origin, dtype=np.float64)
    if f.shape != m.shape:
        raise ValueError(f"force/moment shape mismatch: {f.shape} vs {m.shape}")
    if f.shape[-1] != 3:
        raise ValueError(f"expected (..., 3) force/moment vectors, got {f.shape}")
    if o.shape != (3,):
        raise ValueError(f"expected a (3,) origin, got {o.shape}")

    x0, y0, z0 = o
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    mx, my, mz = m[..., 0], m[..., 1], m[..., 2]
    mx_corrected = mx + fy * z0 - fz * y0
    my_corrected = my - fx * z0 + fz * x0
    return np.stack([mx_corrected, my_corrected, mz], axis=-1)


def compute_cop(
    force: np.ndarray, moment_corrected: np.ndarray, *, f_threshold: float = 15.0
) -> dict[str, np.ndarray]:
    """Steps 3-4: instantaneous centre of pressure with a contact threshold.

    README.md §3.5.3-4:
        `x_cop = -My' / Fz`, `y_cop = Mx' / Fz`, `z_cop = 0`
        below `f_threshold` (default 15.0 N), COP/F/M are all zeroed to
        eliminate the non-contact division singularity.

    Args:
        force: `(..., 3)` `(Fx, Fy, Fz)`.
        moment_corrected: `(..., 3)` `(Mx', My', Mz)`, output of
            `correct_moment_origin`, same leading shape as `force`.
        f_threshold: vertical-force contact threshold in Newtons.

    Returns:
        `{"cop": (..., 3), "force": (..., 3), "moment": (..., 3)}`, all
        zeroed on frames where `Fz < f_threshold`.

    Raises:
        ValueError: mismatched shapes.
    """
    f = np.asarray(force, dtype=np.float64)
    m = np.asarray(moment_corrected, dtype=np.float64)
    if f.shape != m.shape:
        raise ValueError(f"force/moment shape mismatch: {f.shape} vs {m.shape}")
    if f.shape[-1] != 3:
        raise ValueError(f"expected (..., 3) force/moment vectors, got {f.shape}")

    fz = f[..., 2]
    contact = fz >= f_threshold

    with np.errstate(invalid="ignore", divide="ignore"):
        x_cop = -m[..., 1] / fz
        y_cop = m[..., 0] / fz
    z_cop = np.zeros_like(fz)
    cop = np.stack([x_cop, y_cop, z_cop], axis=-1)

    out_cop = np.where(contact[..., np.newaxis], cop, 0.0)
    out_force = np.where(contact[..., np.newaxis], f, 0.0)
    out_moment = np.where(contact[..., np.newaxis], m, 0.0)
    return {"cop": out_cop, "force": out_force, "moment": out_moment}
