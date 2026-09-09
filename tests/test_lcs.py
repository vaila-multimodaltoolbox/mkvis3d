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
