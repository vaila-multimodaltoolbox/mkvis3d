"""Marker-defined coordinate-system orientation analysis."""

from __future__ import annotations

import warnings

import numpy as np

from .biomech_math.rotations import cardan_singularity_margin, rotmat_to_cardan, rotmat_to_quat
from .marker_trial import MarkerTrial

TAIT_BRYAN_SEQUENCES = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")


def marker_frame_orientations(
    trial: MarkerTrial,
    origin_marker: str,
    x_axis_marker: str,
    xy_plane_marker: str,
    *,
    sequences: tuple[str, ...] = TAIT_BRYAN_SEQUENCES,
) -> dict:
    """Build a right-handed frame and report quaternion/Euler trajectories.

    The local X axis points from ``origin_marker`` to ``x_axis_marker``.
    ``xy_plane_marker`` selects the positive half of the local XY plane;
    Z is ``X × temporary-Y`` and Y is recomputed as ``Z × X``.
    """
    if any(sequence not in TAIT_BRYAN_SEQUENCES for sequence in sequences):
        raise ValueError(f"sequences must be selected from {TAIT_BRYAN_SEQUENCES}")
    origin = trial.marker(origin_marker)
    x_point = trial.marker(x_axis_marker)
    plane_point = trial.marker(xy_plane_marker)
    x_raw = x_point - origin
    plane_raw = plane_point - origin
    x_norm = np.linalg.norm(x_raw, axis=1)
    z_raw = np.cross(x_raw, plane_raw)
    z_norm = np.linalg.norm(z_raw, axis=1)
    valid = (
        np.isfinite(origin).all(axis=1)
        & np.isfinite(x_raw).all(axis=1)
        & np.isfinite(plane_raw).all(axis=1)
        & (x_norm > 1e-12)
        & (z_norm > 1e-12)
    )

    rotations = np.full((trial.n_frames, 3, 3), np.nan, dtype=np.float64)
    x_axis = x_raw[valid] / x_norm[valid, None]
    z_axis = z_raw[valid] / z_norm[valid, None]
    y_axis = np.cross(z_axis, x_axis)
    rotations[valid] = np.stack((x_axis, y_axis, z_axis), axis=2)

    quaternions = np.full((trial.n_frames, 4), np.nan, dtype=np.float64)
    euler = {
        sequence: np.full((trial.n_frames, 3), np.nan, dtype=np.float64) for sequence in sequences
    }
    margins = {
        sequence: np.full(trial.n_frames, np.nan, dtype=np.float64) for sequence in sequences
    }
    if valid.any():
        valid_rotations = rotations[valid]
        quaternions[valid] = rotmat_to_quat(valid_rotations)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for sequence in sequences:
                euler[sequence][valid] = rotmat_to_cardan(
                    valid_rotations, sequence=sequence, degrees=True
                )
                margins[sequence][valid] = cardan_singularity_margin(
                    valid_rotations, sequence=sequence, degrees=True
                )

    return {
        "schema_version": 1,
        "definition": {
            "origin": origin_marker,
            "x_axis_point": x_axis_marker,
            "xy_plane_point": xy_plane_marker,
        },
        "quaternion_convention": "scalar-first wxyz",
        "angle_units": "degrees",
        "rotation_matrices": rotations,
        "quaternions": quaternions,
        "euler": euler,
        "gimbal_lock_margin_degrees": margins,
        "valid": valid,
    }
