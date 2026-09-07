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


def plate_frame(
    corners: np.ndarray, *, convention: str = "continuation"
) -> tuple[np.ndarray, np.ndarray]:
    """Return surface centre and local-to-lab rotation from four corners (m).

    Shape (4,3) has one corner per row; C3D shape (3,4) is also accepted.
    ``continuation`` uses EXACTLY the supplied C1+C2-C3-C4 x-axis and
    C1+C4-C2-C3 y-axis. ``c3d`` uses official C3D quadrant order, swapping
    those axes. These conventions have opposite normals: select explicitly
    when reading FORCE_PLATFORM:CORNERS; do not infer from lab vertical.
    Source: https://www.c3d.org/HTML/Documents/forceplatformcorners.htm
    """
    c = np.asarray(corners, dtype=np.float64)
    if c.shape == (3, 4):
        c = c.T
    if c.shape != (4, 3) or not np.isfinite(c).all():
        raise ValueError("corners must be finite (4, 3) or C3D (3, 4)")
    if convention not in ("continuation", "c3d"):
        raise ValueError("corner convention must be 'continuation' or 'c3d'")
    x = c[0] + c[1] - c[2] - c[3]
    y = c[0] + c[3] - c[1] - c[2]
    if convention == "c3d":
        x, y = y, x
    if np.linalg.norm(x) < 1e-12 or np.linalg.norm(y) < 1e-12:
        raise ValueError("corners define a degenerate plate")
    x, y = x / np.linalg.norm(x), y / np.linalg.norm(y)
    if abs(np.dot(x, y)) > 1e-7 or not np.allclose(c[0] + c[2], c[1] + c[3], atol=1e-8, rtol=0):
        raise ValueError("corners must describe an ordered planar rectangle")
    return c.mean(axis=0), np.column_stack([x, y, np.cross(x, y)])


def global_plate_wrench(
    force: np.ndarray,
    surface_moment: np.ndarray,
    corners: np.ndarray,
    *,
    convention: str = "continuation",
    f_threshold: float = 15.0,
) -> dict[str, np.ndarray]:
    """Surface-centred LOCAL wrench -> GLOBAL force, COP and free moment.

    Inputs use N, Nm and m; surface_moment must already be about the plate
    surface centre. Contact is strictly local Fz > threshold, independent of
    plate orientation in the lab. 'moment' in this result is the FREE moment
    at COP, M_surface - COP_local x F, not the surface-centred input moment.
    This prevents double-counting the GRF lever arm in Newton-Euler.
    Inactive samples return zero force/moment/COP plus contact=False.
    """
    f = np.asarray(force, dtype=np.float64)
    m = np.asarray(surface_moment, dtype=np.float64)
    if f.ndim < 1 or f.shape[-1] != 3 or f.shape != m.shape:
        raise ValueError("force and surface_moment must have matching (..., 3) shapes")
    if not np.isfinite(f).all() or not np.isfinite(m).all():
        raise ValueError("force and surface_moment must be finite")
    if not np.isfinite(f_threshold) or f_threshold <= 0:
        raise ValueError("f_threshold must be finite and positive")
    origin, R = plate_frame(corners, convention=convention)
    local = compute_cop(f, m, f_threshold=f_threshold)
    contact = f[..., 2] > f_threshold
    cop = local["cop"]
    free_moment = m - np.cross(cop, f)
    return {
        "cop": np.where(contact[..., None], origin + cop @ R.T, 0.0),
        "force": np.where(contact[..., None], f @ R.T, 0.0),
        "moment": np.where(contact[..., None], free_moment @ R.T, 0.0),
        "contact": contact,
    }
