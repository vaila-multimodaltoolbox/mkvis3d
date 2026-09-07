"""Unit-quaternion orientation algebra and Cardan/Euler extraction.

README.md §3.1 requires orientation to be carried as unit quaternions
`q = [w, x, y, z]` and Cardan/Euler angles to be produced only as a final
*extraction* step, so that gimbal lock cannot corrupt intermediate tracking.
These helpers implement that contract on top of
`scipy.spatial.transform.Rotation`, which already owns the numerically careful
matrix/quaternion/Euler conversions — this module supplies the project's
conventions, batching, and the time-series behaviour scipy does not cover
(sign continuity, singularity margin).

Convention: quaternions are **scalar-first** `(w, x, y, z)`, matching
README.md §3.1 and `/home/preto/data/vaila/vaila/joint_kinematics.py:
rotmat_to_quat_wxyz`. scipy's own `as_quat()` is scalar-last, so every
boundary with scipy reorders explicitly. (vailá's older
`rotation.py:rotmat2quat` documents scalar-first but returns scipy's raw
scalar-last order; that inconsistency is deliberately not reproduced here.)
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

# Cardan/Tait-Bryan sequences use lower-case (intrinsic-free, extrinsic) axis
# letters in scipy; upper-case would mean intrinsic rotations.
DEFAULT_SEQUENCE = "xyz"

_XYZW_FROM_WXYZ = [1, 2, 3, 0]
_WXYZ_FROM_XYZW = [3, 0, 1, 2]


def _as_rotation(rotmats: np.ndarray) -> tuple[Rotation, tuple[int, ...]]:
    """Flatten a `(..., 3, 3)` stack into a scipy Rotation plus its batch shape."""
    arr = np.asarray(rotmats, dtype=np.float64)
    if arr.ndim < 2 or arr.shape[-2:] != (3, 3):
        raise ValueError(f"expected a (..., 3, 3) rotation-matrix stack, got {arr.shape}")
    return Rotation.from_matrix(arr.reshape(-1, 3, 3)), arr.shape[:-2]


def _quat_batch(quats: np.ndarray) -> tuple[np.ndarray, tuple[int, ...]]:
    arr = np.asarray(quats, dtype=np.float64)
    if arr.ndim < 1 or arr.shape[-1] != 4:
        raise ValueError(f"expected a (..., 4) quaternion stack, got {arr.shape}")
    return arr.reshape(-1, 4), arr.shape[:-1]


def normalize_quat(quats: np.ndarray) -> np.ndarray:
    """Scale each quaternion to unit norm.

    Raises:
        ValueError: if any quaternion has (near-)zero norm and therefore
            encodes no orientation at all.
    """
    flat, batch = _quat_batch(quats)
    norms = np.linalg.norm(flat, axis=1, keepdims=True)
    if np.any(norms < 1e-12):
        raise ValueError("cannot normalise a zero-norm quaternion")
    return (flat / norms).reshape(*batch, 4)


def canonicalize_quat(quats: np.ndarray) -> np.ndarray:
    """Flip quaternions to the `w >= 0` hemisphere.

    `q` and `-q` name the same rotation, so a canonical sign makes two
    orientations comparable element-wise.
    """
    flat, batch = _quat_batch(quats)
    flipped = np.where(flat[:, :1] < 0, -flat, flat)
    return flipped.reshape(*batch, 4)


def rotmat_to_quat(rotmats: np.ndarray, *, canonical: bool = True) -> np.ndarray:
    """Convert `(..., 3, 3)` rotation matrices to `(..., 4)` `(w, x, y, z)`."""
    rotation, batch = _as_rotation(rotmats)
    wxyz = rotation.as_quat()[:, _WXYZ_FROM_XYZW]
    if canonical:
        wxyz = np.where(wxyz[:, :1] < 0, -wxyz, wxyz)
    return wxyz.reshape(*batch, 4)


def quat_to_rotmat(quats: np.ndarray) -> np.ndarray:
    """Convert `(..., 4)` `(w, x, y, z)` quaternions to `(..., 3, 3)` matrices."""
    flat, batch = _quat_batch(quats)
    rotation = Rotation.from_quat(flat[:, _XYZW_FROM_WXYZ])
    return rotation.as_matrix().reshape(*batch, 3, 3)


def quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product `a * b` (apply `b` first, then `a`), scalar-first."""
    flat_a, batch = _quat_batch(a)
    flat_b, batch_b = _quat_batch(b)
    if batch != batch_b:
        raise ValueError(f"quaternion batch shapes differ: {batch} vs {batch_b}")
    # Written out rather than composed through scipy: the Hamilton product is
    # four lines, avoids two quaternion<->Rotation conversions, and keeps the
    # scalar-first ordering explicit at the one place it matters most.
    w_a, v_a = flat_a[:, :1], flat_a[:, 1:]
    w_b, v_b = flat_b[:, :1], flat_b[:, 1:]
    w = w_a * w_b - np.sum(v_a * v_b, axis=1, keepdims=True)
    v = w_a * v_b + w_b * v_a + np.cross(v_a, v_b)
    return np.concatenate([w, v], axis=1).reshape(*batch, 4)


def quat_conjugate(quats: np.ndarray) -> np.ndarray:
    """Conjugate (= inverse, for unit quaternions): negate the vector part."""
    flat, batch = _quat_batch(quats)
    out = flat.copy()
    out[:, 1:] *= -1.0
    return out.reshape(*batch, 4)


def quat_angular_distance(a: np.ndarray, b: np.ndarray, *, degrees: bool = False) -> np.ndarray:
    """Geodesic angle between two orientations, in [0, pi] (sign-insensitive)."""
    flat_a, batch = _quat_batch(a)
    flat_b, _ = _quat_batch(b)
    dot = np.abs(np.sum(normalize_quat(flat_a) * normalize_quat(flat_b), axis=1))
    angle = 2.0 * np.arccos(np.clip(dot, -1.0, 1.0))
    if degrees:
        angle = np.degrees(angle)
    return angle.reshape(batch)


def enforce_quat_continuity(quats: np.ndarray, *, axis: int = 0) -> np.ndarray:
    """Remove sign flips along a time series of quaternions.

    Per-frame conversions pick the `q`/`-q` sign independently, which injects
    spurious jumps into an otherwise smooth orientation trajectory — and those
    jumps survive into any derivative taken afterwards. This flips each sample
    to the hemisphere of its predecessor, leaving the rotations unchanged.
    """
    arr = np.asarray(quats, dtype=np.float64)
    if arr.shape[-1] != 4:
        raise ValueError(f"expected a (..., 4) quaternion stack, got {arr.shape}")
    moved = np.moveaxis(arr, axis, 0).copy()
    if moved.shape[0] < 2:
        return arr.copy()
    dots = np.sum(moved[1:] * moved[:-1], axis=-1)
    # A negative running product means an odd number of flips so far.
    flips = np.cumprod(np.where(dots < 0, -1.0, 1.0), axis=0)
    moved[1:] *= flips[..., None]
    return np.moveaxis(moved, 0, axis)


def rotmat_to_cardan(
    rotmats: np.ndarray, *, sequence: str = DEFAULT_SEQUENCE, degrees: bool = True
) -> np.ndarray:
    """Extract Cardan/Euler angles from rotation matrices.

    This is the terminal extraction step of README.md §3.1: track in
    quaternions or matrices, convert to angles only for reporting. Check
    `cardan_singularity_margin` when the second angle may approach ±90°,
    where the first and third angles stop being separately identifiable.
    """
    rotation, batch = _as_rotation(rotmats)
    return rotation.as_euler(sequence, degrees=degrees).reshape(*batch, 3)


def cardan_to_rotmat(
    angles: np.ndarray, *, sequence: str = DEFAULT_SEQUENCE, degrees: bool = True
) -> np.ndarray:
    """Inverse of `rotmat_to_cardan`."""
    arr = np.asarray(angles, dtype=np.float64)
    if arr.ndim < 1 or arr.shape[-1] != 3:
        raise ValueError(f"expected a (..., 3) angle stack, got {arr.shape}")
    rotation = Rotation.from_euler(sequence, arr.reshape(-1, 3), degrees=degrees)
    return rotation.as_matrix().reshape(*arr.shape[:-1], 3, 3)


def quat_to_cardan(
    quats: np.ndarray, *, sequence: str = DEFAULT_SEQUENCE, degrees: bool = True
) -> np.ndarray:
    """Extract Cardan/Euler angles directly from `(w, x, y, z)` quaternions."""
    flat, batch = _quat_batch(quats)
    rotation = Rotation.from_quat(flat[:, _XYZW_FROM_WXYZ])
    return rotation.as_euler(sequence, degrees=degrees).reshape(*batch, 3)


def cardan_singularity_margin(
    rotmats: np.ndarray, *, sequence: str = DEFAULT_SEQUENCE, degrees: bool = True
) -> np.ndarray:
    """How far the middle Cardan angle sits from its ±90° gimbal lock, per sample.

    Returns `90 - |beta|` in degrees (or the radian equivalent). At zero the
    outer two angles trade off freely against each other and their individual
    values are meaningless even though the underlying rotation is perfectly
    well defined — the failure README.md §3.1 requires quaternion tracking to
    avoid.
    """
    angles = rotmat_to_cardan(rotmats, sequence=sequence, degrees=True)
    margin = 90.0 - np.abs(angles[..., 1])
    return margin if degrees else np.radians(margin)


def slerp(q0: np.ndarray, q1: np.ndarray, t: np.ndarray | float) -> np.ndarray:
    """Spherical linear interpolation between two orientations.

    Always takes the shorter arc (antipodal inputs are re-signed first), so
    `t` traverses at a constant angular rate over the smaller of the two
    possible paths.

    Args:
        q0: `(4,)` start orientation, scalar-first.
        q1: `(4,)` end orientation, scalar-first.
        t: scalar or `(K,)` interpolation parameter; 0 gives `q0`, 1 gives
            `q1`. Values outside [0, 1] extrapolate along the same great arc.

    Returns:
        `(4,)` for scalar `t`, else `(K, 4)`.
    """
    a = normalize_quat(np.asarray(q0, dtype=np.float64).reshape(4))
    b = normalize_quat(np.asarray(q1, dtype=np.float64).reshape(4))
    if float(np.dot(a, b)) < 0.0:
        b = -b  # shorter arc

    times = np.atleast_1d(np.asarray(t, dtype=np.float64))
    dot = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if dot > 1.0 - 1e-12:
        # Nearly identical: the arc is shorter than float precision, so
        # normalised linear interpolation is both stable and accurate.
        out = a[None, :] + times[:, None] * (b - a)[None, :]
        out = out / np.linalg.norm(out, axis=1, keepdims=True)
    else:
        theta = np.arccos(dot)
        sin_theta = np.sin(theta)
        w0 = np.sin((1.0 - times) * theta) / sin_theta
        w1 = np.sin(times * theta) / sin_theta
        out = w0[:, None] * a[None, :] + w1[:, None] * b[None, :]

    return out[0] if np.isscalar(t) or np.asarray(t).ndim == 0 else out


def slerp_sequence(times: np.ndarray, quats: np.ndarray, new_times: np.ndarray) -> np.ndarray:
    """Resample an orientation trajectory onto new sample times.

    Delegates to `scipy.spatial.transform.Slerp`, which chains the pairwise
    interpolation above across every key frame.

    Args:
        times: `(N,)` strictly increasing key times.
        quats: `(N, 4)` scalar-first orientations at those times.
        new_times: `(K,)` query times, within `[times[0], times[-1]]`.

    Returns:
        `(K, 4)` scalar-first orientations.
    """
    key_times = np.asarray(times, dtype=np.float64)
    flat, _ = _quat_batch(quats)
    if flat.shape[0] != key_times.shape[0]:
        raise ValueError(
            f"times and quats disagree: {key_times.shape[0]} times vs {flat.shape[0]} quaternions"
        )
    if key_times.size < 2:
        raise ValueError("need at least two key times to interpolate between")

    rotations = Rotation.from_quat(flat[:, _XYZW_FROM_WXYZ])
    interpolated = Slerp(key_times, rotations)(np.asarray(new_times, dtype=np.float64))
    return interpolated.as_quat()[:, _WXYZ_FROM_XYZW]
