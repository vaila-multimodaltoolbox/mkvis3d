"""Laboratory Coordinate System (LCS) transformation following Visual3D specification.

Reference:
- https://wiki.has-motion.com/doku.php?id=visual3d:documentation:pipeline:other_commands:set_laboratory_coordinate_system
- https://www.wiki.has-motion.com/doku.php?id=visual3d:documentation:definitions:laboratory_coordinate_system

In Visual3D:
- The user specifies two principal axis directions: AXIAL_DIRECTION and AP_DIRECTION.
- Visual3D enforces a right-handed Cartesian coordinate system:
    ML_DIRECTION = AP_DIRECTION x AXIAL_DIRECTION
- Canonical target LCS orientation:
    X_lcs = ML (Mediolateral / Right)
    Y_lcs = AP (Anterior-Posterior / Forward progression)
    Z_lcs = Axial (Vertical / Up)
"""

from __future__ import annotations

import numpy as np

from openbiomech.marker_trial import MarkerTrial

# Standard unit basis vectors
DIRECTION_VECTORS: dict[str, np.ndarray] = {
    "+X": np.array([1.0, 0.0, 0.0], dtype=np.float64),
    "-X": np.array([-1.0, 0.0, 0.0], dtype=np.float64),
    "+Y": np.array([0.0, 1.0, 0.0], dtype=np.float64),
    "-Y": np.array([0.0, -1.0, 0.0], dtype=np.float64),
    "+Z": np.array([0.0, 0.0, 1.0], dtype=np.float64),
    "-Z": np.array([0.0, 0.0, -1.0], dtype=np.float64),
}


def parse_direction(dir_str: str) -> tuple[str, np.ndarray]:
    """Normalize and parse axis direction string like '+Z', 'Z', '-Y', 'y'."""
    clean = dir_str.strip().upper()
    if not clean:
        raise ValueError("Direction string cannot be empty")
    if not clean.startswith(("+", "-")):
        clean = "+" + clean
    if clean not in DIRECTION_VECTORS:
        valid_options = ", ".join(DIRECTION_VECTORS.keys())
        raise ValueError(f"Invalid direction '{dir_str}'. Expected one of: {valid_options}")
    return clean, DIRECTION_VECTORS[clean]


def format_vector_as_direction(vec: np.ndarray) -> str:
    """Find the matching canonical direction string for a unit axis vector."""
    for name, v in DIRECTION_VECTORS.items():
        if np.allclose(vec, v, atol=1e-5):
            return name
    return f"[{vec[0]:.2f}, {vec[1]:.2f}, {vec[2]:.2f}]"


def compute_lcs_matrix(ap_direction: str, axial_direction: str) -> tuple[np.ndarray, str]:
    """Compute the 3x3 rotation matrix to transform from raw trial axes to canonical LCS.

    Parameters:
        ap_direction: Anterior-Posterior (progression) direction, e.g. '+Y', '-Y', '+X'.
        axial_direction: Axial (vertical up) direction, e.g. '+Z', '+Y', '-Z'.

    Returns:
        A tuple of (R, ml_direction_str), where:
        - R is a (3, 3) orthonormal rotation matrix with det(R) = +1.
        - ml_direction_str is the calculated right-handed ML axis (e.g. '+X').

    Raises:
        ValueError: if ap_direction and axial_direction are collinear or invalid.
    """
    ap_name, ap_vec = parse_direction(ap_direction)
    axial_name, axial_vec = parse_direction(axial_direction)

    # Check orthogonality
    dot = float(np.dot(ap_vec, axial_vec))
    if abs(dot) > 1e-4:
        raise ValueError(
            f"AP_DIRECTION ({ap_name}) and AXIAL_DIRECTION ({axial_name}) must be orthogonal, "
            f"got dot product = {dot:.4f}"
        )

    # In right-handed Visual3D convention:
    # X_lcs (ML) x Y_lcs (AP) = Z_lcs (Axial)  =>  ML = AP x Axial
    ml_vec = np.cross(ap_vec, axial_vec)
    norm = float(np.linalg.norm(ml_vec))
    if norm < 1e-5:
        raise ValueError("Degenerate axis combination; cross product is zero")
    ml_vec = ml_vec / norm
    ml_name = format_vector_as_direction(ml_vec)

    # Transformation matrix maps [x_raw, y_raw, z_raw] to [x_lcs, y_lcs, z_lcs]:
    # x_lcs = dot(raw, ml_vec)
    # y_lcs = dot(raw, ap_vec)
    # z_lcs = dot(raw, axial_vec)
    rot = np.vstack([ml_vec, ap_vec, axial_vec])

    det = float(np.linalg.det(rot))
    if not np.isclose(det, 1.0, atol=1e-4):
        raise ValueError(f"Matrix determinant must be +1.0 (right-handed rotation), got {det:.4f}")

    return rot, ml_name


# Common presets
LCS_PRESETS: dict[str, dict[str, str]] = {
    "isb_default": {
        "name": "ISB / Vicon / Visual3D (Z-Up, Y-Forward)",
        "axial": "+Z",
        "ap": "+Y",
        "description": "Standard biomechanics: Z is vertical up, Y is progression, X is right.",
    },
    "y_up_bvh": {
        "name": "BVH / Unity / Blender (Y-Up, Z-Forward)",
        "axial": "+Y",
        "ap": "+Z",
        "description": "Common animation/game format: Y is vertical up, Z is forward.",
    },
    "y_up_threejs": {
        "name": "Three.js / OpenGL (Y-Up, -Z-Forward)",
        "axial": "+Y",
        "ap": "-Z",
        "description": "Graphics standard: Y is vertical up, -Z is camera forward.",
    },
    "x_up": {
        "name": "X-Up (X-Vertical, Y-Forward)",
        "axial": "+X",
        "ap": "+Y",
        "description": "Rotated sensor coordinate system with X pointing up.",
    },
    "walkway_x": {
        "name": "Walkway along X (Z-Up, X-Forward)",
        "axial": "+Z",
        "ap": "+X",
        "description": "Gait lab where progression is along +X instead of +Y.",
    },
    "reverse_walkway": {
        "name": "Reverse Walkway (Z-Up, -Y-Forward)",
        "axial": "+Z",
        "ap": "-Y",
        "description": "Subject walking in reverse direction along -Y.",
    },
}


def transform_trial_lcs(
    trial: MarkerTrial,
    ap_direction: str,
    axial_direction: str,
) -> tuple[MarkerTrial, np.ndarray, str]:
    """Transform all marker trajectories in a MarkerTrial to canonical LCS coordinates.

    Coordinates [x, y, z] are rotated by R:
        p_lcs = R @ p_raw

    Returns:
        (transformed_trial, rotation_matrix, ml_direction)
    """
    rot_mat, ml_name = compute_lcs_matrix(ap_direction, axial_direction)

    # Vectorized rotation across all frames and markers:
    # trial.xyz shape is (n_frames, n_markers, 3)
    xyz_transformed = np.einsum("ij,fmj->fmi", rot_mat, trial.xyz)

    new_trial = MarkerTrial(
        labels=trial.labels,
        rate_hz=trial.rate_hz,
        xyz=xyz_transformed,
        residuals=trial.residuals.copy(),
    )
    return new_trial, rot_mat, ml_name
