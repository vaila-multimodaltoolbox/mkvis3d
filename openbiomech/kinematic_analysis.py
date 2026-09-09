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


def build_orthonormal_basis(
    origin_pts: np.ndarray,
    primary_pts: np.ndarray,
    plane_pts: np.ndarray,
    primary_axis: str = "+z",
    plane_axis: str = "+y",
) -> tuple[np.ndarray, np.ndarray]:
    """Build a continuous sequence of 3x3 orthonormal right-handed Cartesian bases.

    Each basis column is guaranteed to be mutually perpendicular (90° angles),
    have unit norm 1 (each versor divided component-by-component by its Euclidean norm),
    and satisfy det(R) = +1.

    Args:
        origin_pts: (N, 3) coordinates of origin.
        primary_pts: (N, 3) coordinates of primary axis target.
        plane_pts: (N, 3) coordinates defining the secondary plane.
        primary_axis: Primary axis name ('+z', '-z', '+y', '-y', '+x', '-x').
        plane_axis: Secondary plane orientation ('+y', '-y', '+x', '-x', '+z', '-z').

    Returns:
        bases: (N, 3, 3) rotation/basis matrices where columns are [e_x, e_y, e_z].
        valid: (N,) boolean mask indicating valid frames.
    """
    n_frames = len(origin_pts)
    v_primary_raw = primary_pts - origin_pts
    v_plane_raw = plane_pts - origin_pts

    norm_primary = np.linalg.norm(v_primary_raw, axis=1)
    norm_plane = np.linalg.norm(v_plane_raw, axis=1)

    # Valid if all points finite and not degenerate
    valid = (
        np.isfinite(origin_pts).all(axis=1)
        & np.isfinite(primary_pts).all(axis=1)
        & np.isfinite(plane_pts).all(axis=1)
        & (norm_primary > 1e-9)
        & (norm_plane > 1e-9)
    )

    bases = np.full((n_frames, 3, 3), np.nan, dtype=np.float64)
    if not valid.any():
        return bases, valid

    # 1. Primary unit versor: divided component-by-component by its norm
    p_sign = -1.0 if primary_axis.startswith("-") else 1.0
    p_axis_char = primary_axis.lstrip("+-").lower()
    e_primary = p_sign * (v_primary_raw[valid] / norm_primary[valid, None])

    # 2. Temporary plane vector
    v_pl = v_plane_raw[valid]

    # 3. Orthogonalize via Gram-Schmidt / cross product
    # Project out component along e_primary
    dot = np.sum(v_pl * e_primary, axis=1, keepdims=True)
    v_ortho = v_pl - dot * e_primary
    norm_ortho = np.linalg.norm(v_ortho, axis=1)

    valid_ortho = norm_ortho > 1e-9
    if not valid_ortho.all():
        # Fallback for collinear plane points: cross with arbitrary axis
        for i in range(len(norm_ortho)):
            if norm_ortho[i] <= 1e-9:
                cand = (
                    np.array([1.0, 0.0, 0.0])
                    if abs(e_primary[i, 0]) < 0.9
                    else np.array([0.0, 1.0, 0.0])
                )
                v_ortho[i] = np.cross(e_primary[i], cand)
                norm_ortho[i] = np.linalg.norm(v_ortho[i])

    e_secondary = v_ortho / norm_ortho[:, None]
    if plane_axis.startswith("-"):
        e_secondary = -e_secondary

    # 4. Third axis via cross product to guarantee right-handed system (det = +1)
    if p_axis_char == "z":
        # Primary is Z
        e_z = e_primary
        if "y" in plane_axis.lower():
            e_y = e_secondary
            e_x = np.cross(e_y, e_z)
            e_x /= np.linalg.norm(e_x, axis=1, keepdims=True)
            # Recompute e_y to guarantee exact 90 degrees
            e_y = np.cross(e_z, e_x)
        else:
            e_x = e_secondary
            e_y = np.cross(e_z, e_x)
            e_y /= np.linalg.norm(e_y, axis=1, keepdims=True)
            e_x = np.cross(e_y, e_z)
    elif p_axis_char == "y":
        # Primary is Y
        e_y = e_primary
        if "z" in plane_axis.lower():
            e_z = e_secondary
            e_x = np.cross(e_y, e_z)
            e_x /= np.linalg.norm(e_x, axis=1, keepdims=True)
            e_z = np.cross(e_x, e_y)
        else:
            e_x = e_secondary
            e_z = np.cross(e_x, e_y)
            e_z /= np.linalg.norm(e_z, axis=1, keepdims=True)
            e_x = np.cross(e_y, e_z)
    else:
        # Primary is X
        e_x = e_primary
        if "y" in plane_axis.lower():
            e_y = e_secondary
            e_z = np.cross(e_x, e_y)
            e_z /= np.linalg.norm(e_z, axis=1, keepdims=True)
            e_y = np.cross(e_z, e_x)
        else:
            e_z = e_secondary
            e_y = np.cross(e_z, e_x)
            e_y /= np.linalg.norm(e_y, axis=1, keepdims=True)
            e_z = np.cross(e_x, e_y)

    # Unit versor division by norm
    e_x /= np.linalg.norm(e_x, axis=1, keepdims=True)
    e_y /= np.linalg.norm(e_y, axis=1, keepdims=True)
    e_z /= np.linalg.norm(e_z, axis=1, keepdims=True)

    # Bases columns: [e_x, e_y, e_z]
    sub_bases = np.stack((e_x, e_y, e_z), axis=2)
    bases[valid] = sub_bases
    return bases, valid


def relative_segment_kinematics(
    s1: np.ndarray,
    s2: np.ndarray,
    sg: np.ndarray | None = None,
    sequence: str = "zxy",
) -> dict:
    """Compute relative rotation matrix MR and kinematics between two segment bases.

    Mathematical formulation:
        MR2 = sg @ s1.T
        MR  = (MR2 @ s2) @ sg.T

    When sg = I (standard laboratory world frame), MR = s1.T @ s2, which is
    the canonical relative rotation matrix expressing segment 2 in segment 1.

    Args:
        s1: (N, 3, 3) orthonormal basis matrices of Segment 1 (proximal).
        s2: (N, 3, 3) orthonormal basis matrices of Segment 2 (distal).
        sg: (N, 3, 3) global/laboratory reference system matrices. Default: I_3x3.
        sequence: Cardan/Euler angle sequence (e.g. 'zxy', 'xyz', 'zyx', 'yxz').

    Returns:
        dict with:
            - MR: (N, 3, 3) relative rotation matrices.
            - MR2: (N, 3, 3) intermediate rotated matrices (sg @ s1.T).
            - euler: (N, 3) Cardan/Euler angles in degrees.
            - quaternions: (N, 4) scalar-first (w, x, y, z) unit quaternions.
            - valid: (N,) boolean mask of valid frames.
    """
    n_frames = len(s1)
    if sg is None:
        sg = np.tile(np.eye(3, dtype=np.float64), (n_frames, 1, 1))
    elif sg.ndim == 2:
        sg = np.tile(sg, (n_frames, 1, 1))

    valid = (
        np.isfinite(s1).all(axis=(1, 2))
        & np.isfinite(s2).all(axis=(1, 2))
        & np.isfinite(sg).all(axis=(1, 2))
    )

    mr = np.full((n_frames, 3, 3), np.nan, dtype=np.float64)
    mr2 = np.full((n_frames, 3, 3), np.nan, dtype=np.float64)
    euler = np.full((n_frames, 3), np.nan, dtype=np.float64)
    quaternions = np.full((n_frames, 4), np.nan, dtype=np.float64)

    if valid.any():
        sub_s1 = s1[valid]
        sub_s2 = s2[valid]
        sub_sg = sg[valid]

        # MR2 = sg @ s1.T
        sub_s1_T = np.swapaxes(sub_s1, -1, -2)
        sub_mr2 = sub_sg @ sub_s1_T

        # MR = (MR2 @ s2) @ sg.T
        sub_sg_T = np.swapaxes(sub_sg, -1, -2)
        sub_mr = (sub_mr2 @ sub_s2) @ sub_sg_T

        mr2[valid] = sub_mr2
        mr[valid] = sub_mr

        # Extract Cardan/Euler angles and unit quaternions
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            euler[valid] = rotmat_to_cardan(sub_mr, sequence=sequence, degrees=True)
            quaternions[valid] = rotmat_to_quat(sub_mr)

    return {
        "schema_version": 1,
        "sequence": sequence,
        "MR": mr,
        "MR2": mr2,
        "euler": euler,
        "quaternions": quaternions,
        "valid": valid,
    }


def evaluate_virtual_point_expression(
    trial: MarkerTrial,
    expression: str,
) -> np.ndarray:
    """Evaluate a mathematical expression using marker points across all frames.

    Expression syntax can use:
        - p['MARKER_NAME'] or markers['MARKER_NAME'] for (N, 3) arrays
        - Standard operators: +, -, *, /, @
        - NumPy functions: np.cross(a, b), np.linalg.norm(a, axis=1), etc.

    Example:
        "(p['RASI'] + p['LASI']) / 2"
    """
    n_frames = trial.n_frames
    p_dict = {label: trial.marker(label) for label in trial.labels}

    allowed_globals = {
        "np": np,
        "p": p_dict,
        "markers": p_dict,
        "abs": abs,
        "min": min,
        "max": max,
    }

    if isinstance(expression, (list, tuple, np.ndarray)):
        result = expression
    else:
        try:
            result = eval(str(expression), {"__builtins__": {}}, allowed_globals)
        except Exception as exc:
            raise ValueError(f"Failed to evaluate expression '{expression}': {exc}") from exc

    result_arr = np.asarray(result, dtype=np.float64)
    if result_arr.shape == (3,):
        result_arr = np.tile(result_arr, (n_frames, 1))
    elif result_arr.shape != (n_frames, 3):
        raise ValueError(
            f"Expression evaluated to shape {result_arr.shape}; expected ({n_frames}, 3)."
        )

    return result_arr


def add_virtual_points_to_trial(
    trial: MarkerTrial,
    virtual_points: list[dict],
) -> MarkerTrial:
    """Add evaluated virtual points to a MarkerTrial dataclass."""
    labels = list(trial.labels)
    xyz = trial.xyz.copy()
    residuals = trial.residuals.copy()
    current_trial = trial

    for vp in virtual_points:
        name = str(vp["name"]).strip()
        expr = str(vp["expression"]).strip()
        pt_coords = evaluate_virtual_point_expression(current_trial, expr)
        if name in labels:
            idx = labels.index(name)
            xyz[:, idx, :] = pt_coords
        else:
            labels.append(name)
            xyz = np.concatenate([xyz, pt_coords[:, None, :]], axis=1)
            residuals = np.concatenate(
                [residuals, np.zeros((trial.n_frames, 1), dtype=np.float64)], axis=1
            )
        current_trial = MarkerTrial(
            labels=tuple(labels),
            rate_hz=trial.rate_hz,
            xyz=xyz,
            residuals=residuals,
            force_plates=trial.force_plates,
            analog_labels=trial.analog_labels,
            analog_units=trial.analog_units,
            analog_rate_hz=trial.analog_rate_hz,
            analog=trial.analog,
        )
    return current_trial


def compute_vector_dot_product_angle(
    u: np.ndarray,
    v: np.ndarray,
    *,
    degrees: bool = True,
) -> np.ndarray | float:
    """Compute the spatial angle between two vectors u and v using the vector dot product.

    Mathematical formulation:
        u · v = ||u|| ||v|| cos(θ)
        cos(θ) = (u · v) / (||u|| ||v||)
        cos_clamped = clamp(cos(θ), -1.0, 1.0)
        θ = arccos(cos_clamped)

    Args:
        u: Vector or trajectory array of shape (3,) or (N, 3).
        v: Vector or trajectory array of shape (3,) or (N, 3).
        degrees: If True (default), returns angle in degrees [0, 180]. If False, in radians [0, π].

    Returns:
        Angle in degrees or radians. Returns shape (N,) for 2D inputs, or float for 1D inputs.
    """
    arr_u = np.asarray(u, dtype=np.float64)
    arr_v = np.asarray(v, dtype=np.float64)

    is_1d = arr_u.ndim == 1 and arr_v.ndim == 1
    if is_1d:
        arr_u = arr_u[None, :]
        arr_v = arr_v[None, :]

    norm_u = np.linalg.norm(arr_u, axis=-1)
    norm_v = np.linalg.norm(arr_v, axis=-1)

    valid = (
        np.isfinite(arr_u).all(axis=-1)
        & np.isfinite(arr_v).all(axis=-1)
        & (norm_u > 1e-12)
        & (norm_v > 1e-12)
    )

    dot = np.sum(arr_u * arr_v, axis=-1)
    angle = np.full(dot.shape, np.nan, dtype=np.float64)

    if valid.any():
        cos_val = np.clip(dot[valid] / (norm_u[valid] * norm_v[valid]), -1.0, 1.0)
        rad = np.arccos(cos_val)
        angle[valid] = np.degrees(rad) if degrees else rad

    if is_1d:
        return float(angle[0]) if np.isfinite(angle[0]) else float("nan")
    return angle


def compute_marker_angle(
    trial: MarkerTrial,
    marker_a: str,
    marker_b: str,
    marker_c: str,
    *,
    degrees: bool = True,
) -> np.ndarray:
    """Compute 3D joint angle at vertex marker_b between marker_a and marker_c across all frames."""
    a = trial.marker(marker_a)
    b = trial.marker(marker_b)
    c = trial.marker(marker_c)
    u = a - b
    v = c - b
    res = compute_vector_dot_product_angle(u, v, degrees=degrees)
    return np.asarray(res, dtype=np.float64)


def compute_two_vector_angle(
    trial: MarkerTrial,
    v1_origin: str,
    v1_target: str,
    v2_origin: str,
    v2_target: str,
    *,
    degrees: bool = True,
) -> np.ndarray:
    """Compute 3D angle between Vector 1 (v1_origin -> v1_target) and Vector 2 (v2_origin -> v2_target)."""
    p1 = trial.marker(v1_origin)
    p2 = trial.marker(v1_target)
    p3 = trial.marker(v2_origin)
    p4 = trial.marker(v2_target)
    u = p2 - p1
    v = p4 - p3
    res = compute_vector_dot_product_angle(u, v, degrees=degrees)
    return np.asarray(res, dtype=np.float64)
