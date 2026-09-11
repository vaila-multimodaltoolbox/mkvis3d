"""Tests for Visual3D Laboratory Coordinate System (LCS) transformation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from openbiomech.biomech_math.lcs import (
    DIRECTION_VECTORS,
    LCS_PRESETS,
    compute_lcs_matrix,
    parse_direction,
    transform_trial_lcs,
)
from openbiomech.c3d_io import read_c3d_native

FIXTURE_C3D = Path(__file__).parent.parent / "data" / "rec3d_20260826_121305_m.c3d"


def test_direction_vectors_are_orthonormal():
    for name, vec in DIRECTION_VECTORS.items():
        assert np.isclose(np.linalg.norm(vec), 1.0)
        parsed_name, parsed_vec = parse_direction(name)
        assert parsed_name == name
        assert np.allclose(parsed_vec, vec)


def test_isb_default_gives_identity():
    # Visual3D default: AP = +Y, Axial = +Z => ML = +X
    rot, ml_name = compute_lcs_matrix("+Y", "+Z")
    assert ml_name == "+X"
    assert np.allclose(rot, np.eye(3))
    assert np.isclose(np.linalg.det(rot), 1.0)


def test_bvh_y_up_convention():
    # BVH standard: AP = +Z, Axial = +Y => ML = +Z x +Y = -X
    rot, ml_name = compute_lcs_matrix("+Z", "+Y")
    assert ml_name == "-X"
    assert np.isclose(np.linalg.det(rot), 1.0)

    # Multiplying a vector along +Y raw gives +Z in LCS (height)
    p_raw = np.array([0.0, 1.5, 0.0])
    p_lcs = rot @ p_raw
    assert np.isclose(p_lcs[2], 1.5)  # Z is height in target LCS


def test_threejs_y_up_convention():
    # Three.js: AP = -Z, Axial = +Y => ML = -Z x +Y = +X
    rot, ml_name = compute_lcs_matrix("-Z", "+Y")
    assert ml_name == "+X"
    assert np.isclose(np.linalg.det(rot), 1.0)


def test_walkway_x_progression():
    # Gait lab along X: AP = +X, Axial = +Z => ML = +X x +Z = -Y
    rot, ml_name = compute_lcs_matrix("+X", "+Z")
    assert ml_name == "-Y"
    assert np.isclose(np.linalg.det(rot), 1.0)


def test_collinear_axes_raise_value_error():
    with pytest.raises(ValueError, match="orthogonal"):
        compute_lcs_matrix("+Z", "+Z")
    with pytest.raises(ValueError, match="orthogonal"):
        compute_lcs_matrix("+Y", "-Y")


def test_invalid_axis_name_raises_value_error():
    with pytest.raises(ValueError, match="Invalid direction"):
        compute_lcs_matrix("W", "+Z")


def test_lcs_presets_dictionary():
    assert "isb_default" in LCS_PRESETS
    assert "y_up_bvh" in LCS_PRESETS
    for _key, preset in LCS_PRESETS.items():
        rot, ml = compute_lcs_matrix(preset["ap"], preset["axial"])
        assert np.isclose(np.linalg.det(rot), 1.0)


def test_transform_trial_preserves_intermarker_distances():
    trial = read_c3d_native(FIXTURE_C3D)
    orig_p1 = trial.marker("p1")
    orig_p2 = trial.marker("p2")
    orig_dist = np.linalg.norm(orig_p1 - orig_p2, axis=-1)

    transformed_trial, rot, ml = transform_trial_lcs(trial, ap_direction="+Z", axial_direction="+Y")
    assert transformed_trial.n_frames == trial.n_frames
    assert transformed_trial.n_markers == trial.n_markers
    assert transformed_trial.rate_hz == trial.rate_hz

    new_p1 = transformed_trial.marker("p1")
    new_p2 = transformed_trial.marker("p2")
    new_dist = np.linalg.norm(new_p1 - new_p2, axis=-1)

    # Rigid rotation preserves all Euclidean distances exactly
    assert np.allclose(orig_dist, new_dist, atol=1e-12)


def test_compute_reference_system_matrix():
    from openbiomech.biomech_math.lcs import compute_reference_system_matrix

    # Identity
    R, det = compute_reference_system_matrix("+X", "+Y", "+Z")
    assert np.allclose(R, np.eye(3))
    assert np.isclose(det, 1.0)

    # Invert X
    R, det = compute_reference_system_matrix("-X", "+Y", "+Z")
    assert np.allclose(R, np.diag([-1, 1, 1]))
    assert np.isclose(det, -1.0)

    # Y-up right handed: X->-X, Y->+Z, Z->+Y
    R, det = compute_reference_system_matrix("-X", "+Z", "+Y")
    assert np.isclose(det, 1.0)
    p = np.array([1.0, 2.0, 3.0])
    p_trans = R @ p
    assert np.allclose(p_trans, [-1.0, 3.0, 2.0])

    # Collinear / repeated axis raises ValueError
    with pytest.raises(ValueError, match="independent"):
        compute_reference_system_matrix("+X", "+X", "+Z")


def test_transform_trial_reference_system_with_translation():
    from openbiomech.biomech_math.lcs import transform_trial_reference_system

    trial = read_c3d_native(FIXTURE_C3D)
    translation = (1.5, -2.0, 0.5)
    transformed, R, det = transform_trial_reference_system(
        trial, x_axis="+X", y_axis="+Y", z_axis="+Z", translation=translation
    )
    assert transformed.n_frames == trial.n_frames
    assert np.allclose(transformed.xyz, trial.xyz + np.array(translation))

    # Test with rotation and translation
    transformed_rot, R, det = transform_trial_reference_system(
        trial, x_axis="-X", y_axis="+Z", z_axis="+Y", translation=translation
    )
    orig_p1 = trial.marker("p1")
    orig_p2 = trial.marker("p2")
    orig_dist = np.linalg.norm(orig_p1 - orig_p2, axis=-1)

    new_p1 = transformed_rot.marker("p1")
    new_p2 = transformed_rot.marker("p2")
    new_dist = np.linalg.norm(new_p1 - new_p2, axis=-1)
    assert np.allclose(orig_dist, new_dist, atol=1e-12)


def test_verify_reference_system_orientation():
    from openbiomech.biomech_math.lcs import (
        verify_reference_system_orientation,
        verify_right_handed_cross_products,
    )

    # Canonical standard right-handed: X, Y, Z (det = +1.0)
    orient_rh, info_rh = verify_reference_system_orientation("+X", "+Y", "+Z")
    assert orient_rh == "right_handed"
    assert info_rh["det"] == "+1.0"
    assert info_rh["expected_z_rh"] == "+Z"

    # Left-Hand Rule: Swap X ↔ Y (Vicon / Blender standard: det = -1.0)
    orient_lh, info_lh = verify_reference_system_orientation("+Y", "+X", "+Z")
    assert orient_lh == "left_handed"
    assert info_lh["det"] == "-1.0"
    assert info_lh["expected_z_lh"] == "+Z"

    # Monocular vaila: X=+X, Y=+Z, Z=-Y (det = +1.0)
    orient_mono, info_mono = verify_reference_system_orientation("+X", "+Z", "-Y")
    assert orient_mono == "right_handed"
    assert info_mono["det"] == "+1.0"
    assert info_mono["expected_z_rh"] == "-Y"

    # Backward compatibility
    is_rh, info = verify_right_handed_cross_products("+X", "+Y", "+Z")
    assert is_rh is True
    is_rh_lh, _ = verify_right_handed_cross_products("+Y", "+X", "+Z")
    assert is_rh_lh is False


def test_transform_trial_monocular_to_standard():
    from openbiomech.biomech_math.lcs import transform_trial_monocular_to_standard

    trial = read_c3d_native(FIXTURE_C3D)
    transformed, R, (tx, ty, tz) = transform_trial_monocular_to_standard(
        trial, auto_floor_z=True, auto_center_xy=True
    )
    assert transformed.n_frames == trial.n_frames
    assert np.isclose(np.linalg.det(R), 1.0)
    # Floor to Z=0 means minimum Z coordinate is at 0.0
    assert np.isclose(np.nanmin(transformed.xyz[..., 2]), 0.0, atol=1e-6)
    # Center X/Y means mean X and Y are at 0.0
    assert np.isclose(np.nanmean(transformed.xyz[..., 0]), 0.0, atol=1e-6)
    assert np.isclose(np.nanmean(transformed.xyz[..., 1]), 0.0, atol=1e-6)


def test_transform_trial_monocular_jjkabuto_file():
    from openbiomech.biomech_math.lcs import transform_trial_monocular_to_standard

    kabuto_path = Path(
        "/home/preto/data/jjkabuto/c3d/processed_linear_butterworth_cut5_0_20260908_171307/csv2c3d_20260908_171334/JJ_Kabuto_id_00_mhr70_3d_butterworth.c3d"
    )
    if not kabuto_path.is_file():
        pytest.skip("JJ_Kabuto file not available in test environment")

    trial = read_c3d_native(kabuto_path)
    transformed, R, (tx, ty, tz) = transform_trial_monocular_to_standard(
        trial, auto_floor_z=True, auto_center_xy=True
    )
    assert transformed.n_frames == trial.n_frames
    assert np.isclose(np.linalg.det(R), 1.0)
    labels = list(transformed.labels)
    # Nose Z should be greater than ankles Z (Z is up)
    nose = labels.index("NOSE")
    r_ank = labels.index("RIGHT_ANKLE")
    assert transformed.xyz[0, nose, 2] > transformed.xyz[0, r_ank, 2]
    # Min Z on floor = 0.0
    assert np.isclose(np.nanmin(transformed.xyz[..., 2]), 0.0, atol=1e-5)
    # Forward progression is along Y
    y_range = np.nanmax(transformed.xyz[..., 1]) - np.nanmin(transformed.xyz[..., 1])
    assert y_range > 0.5
