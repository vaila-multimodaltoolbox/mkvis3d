"""Tests for `openbiomech/inverse_dynamics/newton_euler.py`."""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.inverse_dynamics.newton_euler import GRAVITY, newton_euler_step


def test_static_equilibrium_reduces_to_lever_arm_cross_product():
    # Hand-computed: I=0, w=0, w_dot=0, F_distal=0, M_distal=0, a_com=g
    # (segment in free fall / no net force) -> F_proximal = m*(g-g) = 0,
    # so the only surviving term is M_proximal = -(r_proximal x F_proximal),
    # which is trivially 0 too. Use a_com=0 instead (segment static, held
    # up against gravity) so F_proximal = m*(0-g) = m*(0,0,9.80665) is
    # non-zero and the lever-arm term is verifiable by hand.
    mass = 2.0
    result = newton_euler_step(
        mass=mass,
        com_acceleration=np.zeros(3),
        inertia_tensor=np.zeros((3, 3)),
        angular_velocity=np.zeros(3),
        angular_acceleration=np.zeros(3),
        distal_force=np.zeros(3),
        distal_moment=np.zeros(3),
        r_proximal=np.array([0.1, 0.0, 0.0]),
        r_distal=np.zeros(3),
    )

    # F_proximal = m*(0 - g) = 2.0 * (0, 0, 9.80665) = (0, 0, 19.6133)
    expected_force = mass * (-GRAVITY)
    assert np.allclose(result["force_proximal"], expected_force)

    # r_proximal x F_proximal = (0.1,0,0) x (0,0,19.6133) = (0, -1.96133, 0)
    # M_proximal = -(that) = (0, 1.96133, 0)
    assert np.allclose(result["moment_proximal"], [0.0, 1.96133, 0.0])


def test_gyroscopic_term_isolated_with_zero_lever_arms_and_no_reaction():
    # I=diag(1,2,3), w=(0,1,2), w_dot=0, all reaction/lever terms zero,
    # a_com=g so F_proximal=0.
    # I*w = (0, 2, 6); w x (I*w) = (0,1,2) x (0,2,6)
    #     = (1*6-2*2, 2*0-0*6, 0*2-1*0) = (2, 0, 0)
    result = newton_euler_step(
        mass=1.0,
        com_acceleration=GRAVITY,
        inertia_tensor=np.diag([1.0, 2.0, 3.0]),
        angular_velocity=np.array([0.0, 1.0, 2.0]),
        angular_acceleration=np.zeros(3),
        distal_force=np.zeros(3),
        distal_moment=np.zeros(3),
        r_proximal=np.zeros(3),
        r_distal=np.zeros(3),
    )
    assert np.allclose(result["force_proximal"], 0.0)
    assert np.allclose(result["moment_proximal"], [2.0, 0.0, 0.0])


def test_is_vectorized_over_frames():
    n_frames = 4
    result = newton_euler_step(
        mass=1.5,
        com_acceleration=np.tile(GRAVITY, (n_frames, 1)),
        inertia_tensor=np.tile(np.zeros((3, 3)), (n_frames, 1, 1)),
        angular_velocity=np.zeros((n_frames, 3)),
        angular_acceleration=np.zeros((n_frames, 3)),
        distal_force=np.zeros((n_frames, 3)),
        distal_moment=np.zeros((n_frames, 3)),
        r_proximal=np.zeros((n_frames, 3)),
        r_distal=np.zeros((n_frames, 3)),
    )
    assert result["force_proximal"].shape == (n_frames, 3)
    assert result["moment_proximal"].shape == (n_frames, 3)
    assert np.allclose(result["force_proximal"], 0.0)
    assert np.allclose(result["moment_proximal"], 0.0)


def test_distal_reaction_and_lever_arms_carry_through():
    # Distal segment pushes back with a known force/moment; proximal
    # balance must subtract them per the formula.
    result = newton_euler_step(
        mass=1.0,
        com_acceleration=GRAVITY,  # F_proximal contribution from mass term = 0
        inertia_tensor=np.zeros((3, 3)),
        angular_velocity=np.zeros(3),
        angular_acceleration=np.zeros(3),
        distal_force=np.array([1.0, 0.0, 0.0]),
        distal_moment=np.array([0.0, 0.0, 5.0]),
        r_proximal=np.zeros(3),
        r_distal=np.zeros(3),
    )
    # F_proximal = m*(g-g) - F_distal = -F_distal
    assert np.allclose(result["force_proximal"], [-1.0, 0.0, 0.0])
    # M_proximal = 0 - M_distal - 0 - 0 = -M_distal
    assert np.allclose(result["moment_proximal"], [0.0, 0.0, -5.0])


def test_rejects_mismatched_shapes():
    with pytest.raises(ValueError, match="shape mismatch"):
        newton_euler_step(
            mass=1.0,
            com_acceleration=np.zeros(3),
            inertia_tensor=np.zeros((3, 3)),
            angular_velocity=np.zeros(3),
            angular_acceleration=np.zeros(3),
            distal_force=np.zeros(4),  # wrong
            distal_moment=np.zeros(3),
            r_proximal=np.zeros(3),
            r_distal=np.zeros(3),
        )


def test_rejects_wrong_inertia_shape():
    with pytest.raises(ValueError, match="inertia_tensor shape"):
        newton_euler_step(
            mass=1.0,
            com_acceleration=np.zeros(3),
            inertia_tensor=np.zeros((4, 4)),
            angular_velocity=np.zeros(3),
            angular_acceleration=np.zeros(3),
            distal_force=np.zeros(3),
            distal_moment=np.zeros(3),
            r_proximal=np.zeros(3),
            r_distal=np.zeros(3),
        )
