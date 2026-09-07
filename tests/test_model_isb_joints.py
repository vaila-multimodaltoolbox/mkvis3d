"""Tests for `openbiomech/model/isb_joints.py` (generic Grood & Suntay JCS math)."""

from __future__ import annotations

import numpy as np

from openbiomech.model.isb_joints import decompose_joint_angular_velocity, joint_floating_axis


def test_floating_axis_is_perpendicular_to_both_fixed_axes():
    e_flex = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    e_rot = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])

    e_float = joint_floating_axis(e_flex, e_rot)

    assert np.allclose(np.sum(e_float * e_flex, axis=-1), 0.0, atol=1e-12)
    assert np.allclose(np.sum(e_float * e_rot, axis=-1), 0.0, atol=1e-12)
    assert np.allclose(np.linalg.norm(e_float, axis=-1), 1.0)


def test_floating_axis_matches_hand_worked_orthogonal_case():
    # e_flex = x, e_rot = z -> e_flex x e_rot = x cross z = -y
    e_float = joint_floating_axis(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]))
    assert np.allclose(e_float, [0.0, -1.0, 0.0])


def test_floating_axis_undefined_when_fixed_axes_parallel():
    e_float = joint_floating_axis(np.array([1.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    assert np.all(np.isnan(e_float))


def test_floating_axis_rejects_mismatched_shapes():
    import pytest

    with pytest.raises(ValueError, match="shape mismatch"):
        joint_floating_axis(np.zeros((3,)), np.zeros((2, 3)))


def test_decompose_recovers_known_orthogonal_coefficients():
    e_flex = np.array([1.0, 0.0, 0.0])
    e_rot = np.array([0.0, 0.0, 1.0])
    e_float = joint_floating_axis(e_flex, e_rot)  # = (0,-1,0)

    alpha_dot, beta_dot, gamma_dot = 0.5, -0.2, 1.3
    omega = alpha_dot * e_flex + beta_dot * e_float + gamma_dot * e_rot

    coeffs = decompose_joint_angular_velocity(omega, e_flex, e_float, e_rot)
    assert np.allclose(coeffs, [alpha_dot, beta_dot, gamma_dot])


def test_decompose_recovers_known_nonorthogonal_coefficients():
    # e_flex and e_rot at 60 degrees -> non-orthogonal basis, still solvable
    e_flex = np.array([1.0, 0.0, 0.0])
    e_rot = np.array([np.cos(np.pi / 3), np.sin(np.pi / 3), 0.0])
    e_float = joint_floating_axis(e_flex, e_rot)

    alpha_dot, beta_dot, gamma_dot = 2.0, 0.7, -1.1
    omega = alpha_dot * e_flex + beta_dot * e_float + gamma_dot * e_rot

    coeffs = decompose_joint_angular_velocity(omega, e_flex, e_float, e_rot)
    assert np.allclose(coeffs, [alpha_dot, beta_dot, gamma_dot])


def test_decompose_is_vectorized_over_frames():
    e_flex = np.tile([1.0, 0.0, 0.0], (5, 1))
    e_rot = np.tile([0.0, 0.0, 1.0], (5, 1))
    e_float = joint_floating_axis(e_flex, e_rot)
    coeffs_true = np.arange(15, dtype=np.float64).reshape(5, 3)
    omega = (
        coeffs_true[:, :1] * e_flex + coeffs_true[:, 1:2] * e_float + coeffs_true[:, 2:3] * e_rot
    )

    coeffs = decompose_joint_angular_velocity(omega, e_flex, e_float, e_rot)
    assert coeffs.shape == (5, 3)
    assert np.allclose(coeffs, coeffs_true)


def test_decompose_nan_when_basis_degenerate():
    e_flex = np.array([1.0, 0.0, 0.0])
    e_rot = np.array([1.0, 0.0, 0.0])  # parallel -> e_float NaN -> basis singular
    e_float = joint_floating_axis(e_flex, e_rot)

    coeffs = decompose_joint_angular_velocity(np.array([1.0, 2.0, 3.0]), e_flex, e_float, e_rot)
    assert np.all(np.isnan(coeffs))


def test_decompose_rejects_mismatched_shapes():
    import pytest

    e_flex = np.zeros((3,))
    with pytest.raises(ValueError, match="shape mismatch"):
        decompose_joint_angular_velocity(np.zeros((3,)), e_flex, e_flex, np.zeros((2, 3)))
