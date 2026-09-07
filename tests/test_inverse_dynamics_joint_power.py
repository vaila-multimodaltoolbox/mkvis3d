"""Tests for `openbiomech/inverse_dynamics/joint_power.py`."""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.inverse_dynamics.joint_power import joint_power


def test_hand_worked_dot_product():
    # M = (1, 2, 3), w_distal = (0, 0, 4), w_proximal = (0, 0, 1)
    # -> w_distal - w_proximal = (0, 0, 3); M . that = 3*3 = 9
    p = joint_power(np.array([1.0, 2.0, 3.0]), np.array([0.0, 0.0, 4.0]), np.array([0.0, 0.0, 1.0]))
    assert np.isclose(p, 9.0)


def test_zero_relative_angular_velocity_gives_zero_power():
    omega = np.array([1.0, 2.0, 3.0])
    p = joint_power(np.array([5.0, 5.0, 5.0]), omega, omega)
    assert np.isclose(p, 0.0)


def test_perpendicular_moment_and_relative_velocity_gives_zero_power():
    p = joint_power(np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 0.0]))
    assert np.isclose(p, 0.0)


def test_is_vectorized_over_frames():
    n_frames = 4
    moment = np.tile([1.0, 0.0, 0.0], (n_frames, 1))
    omega_distal = np.tile([2.0, 0.0, 0.0], (n_frames, 1))
    omega_proximal = np.zeros((n_frames, 3))

    p = joint_power(moment, omega_distal, omega_proximal)

    assert p.shape == (n_frames,)
    assert np.allclose(p, 2.0)


def test_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        joint_power(np.zeros(3), np.zeros(3), np.zeros(4))


def test_rejects_wrong_trailing_dim():
    with pytest.raises(ValueError, match=r"\(\.\.\., 3\)"):
        joint_power(np.zeros(4), np.zeros(4), np.zeros(4))
