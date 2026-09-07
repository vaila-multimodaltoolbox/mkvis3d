"""Tests for `openbiomech/inverse_dynamics/force_plate.py`.

Includes the loop's required synthetic force-plate fixture: the golden
`data/` trial carries no analog/force channels
(`../CLAUDE.md` §Data), so Phase 4 needs its own, built here with
hand-computed expected values rather than any external oracle.
"""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.inverse_dynamics.force_plate import (
    compute_cop,
    correct_moment_origin,
    raw_channels_to_forces,
)


def test_raw_channels_identity_matrix_passes_voltages_through():
    voltages = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    forces = raw_channels_to_forces(voltages, np.eye(6))
    assert np.allclose(forces, voltages)


def test_raw_channels_diagonal_calibration_scales_each_channel():
    voltages = np.array([[1.0, 1.0, 1.0, 1.0, 1.0, 1.0], [2.0, 2.0, 2.0, 2.0, 2.0, 2.0]])
    scale = np.diag([100.0, 100.0, 500.0, 50.0, 50.0, 20.0])
    forces = raw_channels_to_forces(voltages, scale)
    expected = voltages * np.array([100.0, 100.0, 500.0, 50.0, 50.0, 20.0])
    assert np.allclose(forces, expected)


def test_raw_channels_rejects_wrong_shapes():
    with pytest.raises(ValueError, match="voltage channels"):
        raw_channels_to_forces(np.zeros(5), np.eye(6))
    with pytest.raises(ValueError, match="calibration matrix"):
        raw_channels_to_forces(np.zeros(6), np.eye(5))


def test_moment_origin_correction_hand_worked_example():
    # Hand-computed: F = (10, 5, 200) N, M = (20, -10, 3) Nm,
    # origin (x0, y0, z0) = (0, 0, -0.005) m (top surface 5mm above sensor).
    force = np.array([10.0, 5.0, 200.0])
    moment = np.array([20.0, -10.0, 3.0])
    origin = np.array([0.0, 0.0, -0.005])

    corrected = correct_moment_origin(force, moment, origin)

    # Mx' = Mx + Fy*z0 - Fz*y0 = 20 + 5*(-0.005) - 200*0 = 19.975
    # My' = My - Fx*z0 + Fz*x0 = -10 - 10*(-0.005) + 200*0 = -9.95
    # Mz unaffected.
    assert np.allclose(corrected, [19.975, -9.95, 3.0])


def test_moment_origin_correction_zero_offset_is_identity():
    force = np.array([1.0, 2.0, 3.0])
    moment = np.array([4.0, 5.0, 6.0])
    corrected = correct_moment_origin(force, moment, np.zeros(3))
    assert np.allclose(corrected, moment)


def test_moment_origin_correction_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        correct_moment_origin(np.zeros(3), np.zeros(4), np.zeros(3))


def test_cop_hand_worked_example_continues_from_moment_correction():
    # Continuing the hand-worked example above: Fz=200, Mx'=19.975, My'=-9.95.
    force = np.array([10.0, 5.0, 200.0])
    corrected_moment = np.array([19.975, -9.95, 3.0])

    result = compute_cop(force, corrected_moment)

    # x_cop = -My'/Fz = 9.95/200 = 0.04975
    # y_cop = Mx'/Fz = 19.975/200 = 0.099875
    assert np.allclose(result["cop"], [0.04975, 0.099875, 0.0])
    assert np.allclose(result["force"], force)
    assert np.allclose(result["moment"], corrected_moment)


def test_cop_centered_load_gives_zero_cop():
    force = np.array([0.0, 0.0, 100.0])
    moment = np.array([0.0, 0.0, 0.0])
    result = compute_cop(force, moment)
    assert np.allclose(result["cop"], [0.0, 0.0, 0.0])


def test_cop_below_threshold_zeroes_everything():
    force = np.array([10.0, 5.0, 10.0])  # Fz = 10 N < default 15 N threshold
    moment = np.array([20.0, -10.0, 3.0])
    result = compute_cop(force, moment)
    assert np.allclose(result["cop"], [0.0, 0.0, 0.0])
    assert np.allclose(result["force"], [0.0, 0.0, 0.0])
    assert np.allclose(result["moment"], [0.0, 0.0, 0.0])


def test_cop_is_vectorized_over_frames_synthetic_trial():
    # Synthetic 10-frame "trial": 5 stance frames (Fz above threshold) with a
    # constant known COP, 5 swing frames (Fz = 0) that must zero out.
    n_frames = 10
    force = np.zeros((n_frames, 3))
    moment = np.zeros((n_frames, 3))
    force[:5] = [0.0, 0.0, 500.0]
    moment[:5] = [50.0, -25.0, 0.0]  # -> x_cop=0.05, y_cop=0.1 for each stance frame

    result = compute_cop(force, moment)

    assert np.allclose(result["cop"][:5], [0.05, 0.1, 0.0])
    assert np.allclose(result["cop"][5:], 0.0)
    assert np.allclose(result["force"][5:], 0.0)


def test_cop_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        compute_cop(np.zeros(3), np.zeros(4))
