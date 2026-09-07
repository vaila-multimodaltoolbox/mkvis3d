"""Phase-2 verifier: quaternion algebra, Cardan extraction and SLERP.

Ground truth is analytic throughout — closed-form rotations whose quaternion
and Euler representations are known by hand — so these are level-1
deterministic checks rather than agreement with another implementation.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from openbiomech.biomech_math import (
    canonicalize_quat,
    cardan_singularity_margin,
    cardan_to_rotmat,
    enforce_quat_continuity,
    kabsch,
    normalize_quat,
    quat_angular_distance,
    quat_conjugate,
    quat_multiply,
    quat_to_cardan,
    quat_to_rotmat,
    rotmat_to_cardan,
    rotmat_to_quat,
    slerp,
    slerp_sequence,
)

SQRT_HALF = np.sqrt(0.5)


def _rotation_about_z(degrees: float) -> np.ndarray:
    theta = np.radians(degrees)
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _random_rotations(n: int, seed: int = 0) -> np.ndarray:
    return Rotation.random(n, rng=np.random.default_rng(seed)).as_matrix()


# --------------------------------------------------------------------------
# Quaternion conventions and round trips
# --------------------------------------------------------------------------


def test_identity_matrix_is_scalar_first_unit_quaternion():
    """The scalar-first convention is the whole point: w comes first."""
    assert np.allclose(rotmat_to_quat(np.eye(3)), [1.0, 0.0, 0.0, 0.0])


def test_known_quaternion_for_90_degree_z_rotation():
    """A 90° turn about z is (cos45, 0, 0, sin45) scalar-first."""
    quat = rotmat_to_quat(_rotation_about_z(90.0))
    assert np.allclose(quat, [SQRT_HALF, 0.0, 0.0, SQRT_HALF])
    # Scalar-LAST would put the sine in slot 0 -- guard against a silent swap.
    assert quat[0] == pytest.approx(SQRT_HALF)
    assert quat[3] == pytest.approx(SQRT_HALF)


def test_quaternion_round_trip_over_random_rotations():
    rotmats = _random_rotations(64, seed=7)
    assert np.allclose(quat_to_rotmat(rotmat_to_quat(rotmats)), rotmats, atol=1e-12)


def test_quaternions_are_unit_norm_and_canonical():
    quats = rotmat_to_quat(_random_rotations(64, seed=8))
    assert np.allclose(np.linalg.norm(quats, axis=-1), 1.0, atol=1e-12)
    assert np.all(quats[:, 0] >= 0.0)  # canonical hemisphere


def test_canonicalize_and_normalize_quat():
    raw = np.array([[-2.0, 0.0, 0.0, 0.0], [0.0, 3.0, 0.0, 0.0]])
    assert np.allclose(normalize_quat(raw), [[-1.0, 0, 0, 0], [0, 1.0, 0, 0]])
    assert np.allclose(canonicalize_quat(normalize_quat(raw))[0], [1.0, 0, 0, 0])
    with pytest.raises(ValueError, match="zero-norm"):
        normalize_quat(np.zeros(4))


def test_batched_shapes_are_preserved():
    rotmats = _random_rotations(12, seed=9).reshape(3, 4, 3, 3)
    quats = rotmat_to_quat(rotmats)
    assert quats.shape == (3, 4, 4)
    assert quat_to_rotmat(quats).shape == (3, 4, 3, 3)
    assert rotmat_to_cardan(rotmats).shape == (3, 4, 3)


def test_quat_multiply_composes_in_matrix_order():
    """q_a * q_b must equal R_a @ R_b (apply b first)."""
    a = _rotation_about_z(30.0)
    b = cardan_to_rotmat(np.array([20.0, 0.0, 0.0]))
    product = quat_multiply(rotmat_to_quat(a), rotmat_to_quat(b))
    assert np.allclose(quat_to_rotmat(product), a @ b, atol=1e-12)


def test_quat_conjugate_inverts():
    quats = rotmat_to_quat(_random_rotations(16, seed=10))
    identity = quat_multiply(quats, quat_conjugate(quats))
    assert np.allclose(canonicalize_quat(identity), [1.0, 0.0, 0.0, 0.0], atol=1e-12)


def test_quat_angular_distance_matches_known_angles():
    q0 = rotmat_to_quat(np.eye(3))
    for angle in (0.0, 30.0, 90.0, 179.0):
        q1 = rotmat_to_quat(_rotation_about_z(angle))
        assert quat_angular_distance(q0, q1, degrees=True) == pytest.approx(angle, abs=1e-9)


def test_quat_angular_distance_ignores_sign():
    q = rotmat_to_quat(_rotation_about_z(40.0))
    assert quat_angular_distance(q, -q, degrees=True) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# Sign continuity along a time series
# --------------------------------------------------------------------------


def test_enforce_quat_continuity_removes_sign_flips():
    angles = np.linspace(0.0, 120.0, 40)
    quats = np.stack([rotmat_to_quat(_rotation_about_z(a)) for a in angles])
    flipped = quats.copy()
    flipped[10:25] *= -1.0  # the flips a per-frame conversion can introduce

    fixed = enforce_quat_continuity(flipped)

    # Same rotations throughout ...
    assert np.allclose(quat_to_rotmat(fixed), quat_to_rotmat(flipped), atol=1e-12)
    # ... but now smooth: no step larger than the true per-sample motion.
    steps = np.linalg.norm(np.diff(fixed, axis=0), axis=1)
    assert steps.max() < 0.1
    assert np.linalg.norm(np.diff(flipped, axis=0), axis=1).max() > 1.0


def test_enforce_quat_continuity_is_a_noop_on_short_input():
    single = rotmat_to_quat(_rotation_about_z(15.0))[None, :]
    assert np.allclose(enforce_quat_continuity(single), single)


# --------------------------------------------------------------------------
# Cardan / Euler extraction
# --------------------------------------------------------------------------


def test_cardan_round_trip_away_from_singularity():
    angles = np.array([[10.0, 20.0, 30.0], [-45.0, 5.0, 80.0], [0.0, 0.0, 0.0]])
    assert np.allclose(rotmat_to_cardan(cardan_to_rotmat(angles)), angles, atol=1e-9)


def test_cardan_known_single_axis_values():
    assert np.allclose(rotmat_to_cardan(_rotation_about_z(35.0)), [0.0, 0.0, 35.0], atol=1e-9)


def test_quat_to_cardan_agrees_with_matrix_route():
    rotmats = _random_rotations(32, seed=11)
    assert np.allclose(
        quat_to_cardan(rotmat_to_quat(rotmats)), rotmat_to_cardan(rotmats), atol=1e-9
    )


def test_cardan_singularity_margin_flags_gimbal_lock():
    """At beta = ±90° the outer two angles are no longer separable."""
    safe = cardan_to_rotmat(np.array([10.0, 20.0, 30.0]))
    locked = cardan_to_rotmat(np.array([10.0, 90.0, 30.0]))

    assert cardan_singularity_margin(safe) == pytest.approx(70.0, abs=1e-6)
    # scipy itself reports the lock, and zeroes the third angle to cope.
    with pytest.warns(UserWarning, match="Gimbal lock"):
        assert cardan_singularity_margin(locked) == pytest.approx(0.0, abs=1e-6)

    # The rotation itself is fine; only the angle *extraction* degenerates --
    # which is why README.md §3.1 tracks orientation as quaternions.
    assert np.allclose(quat_to_rotmat(rotmat_to_quat(locked)), locked, atol=1e-12)


def test_cardan_extraction_is_unstable_at_gimbal_lock_but_quaternions_are_not():
    a = cardan_to_rotmat(np.array([10.0, 90.0, 30.0]))
    b = cardan_to_rotmat(np.array([40.0, 90.0, 60.0]))  # same rotation, alpha+gamma equal

    # Wildly different Cardan triples, yet the orientations coincide.
    assert np.allclose(a, b, atol=1e-9)
    assert quat_angular_distance(rotmat_to_quat(a), rotmat_to_quat(b), degrees=True) < 1e-6


# --------------------------------------------------------------------------
# SLERP
# --------------------------------------------------------------------------


def test_slerp_hits_its_endpoints():
    q0 = rotmat_to_quat(np.eye(3))
    q1 = rotmat_to_quat(_rotation_about_z(90.0))
    assert np.allclose(slerp(q0, q1, 0.0), q0, atol=1e-12)
    assert np.allclose(slerp(q0, q1, 1.0), q1, atol=1e-12)


def test_slerp_midpoint_is_the_half_rotation():
    q0 = rotmat_to_quat(np.eye(3))
    q1 = rotmat_to_quat(_rotation_about_z(90.0))
    assert np.allclose(quat_to_rotmat(slerp(q0, q1, 0.5)), _rotation_about_z(45.0), atol=1e-12)


def test_slerp_has_constant_angular_rate():
    q0 = rotmat_to_quat(np.eye(3))
    q1 = rotmat_to_quat(_rotation_about_z(120.0))
    samples = slerp(q0, q1, np.linspace(0.0, 1.0, 13))

    steps = quat_angular_distance(samples[:-1], samples[1:], degrees=True)
    assert np.allclose(steps, 10.0, atol=1e-9)  # 120° over 12 equal steps


def test_slerp_takes_the_short_arc_for_antipodal_input():
    q0 = rotmat_to_quat(np.eye(3))
    q1 = -rotmat_to_quat(_rotation_about_z(20.0))  # same rotation, opposite sign
    midpoint = slerp(q0, q1, 0.5)
    assert quat_angular_distance(q0, midpoint, degrees=True) == pytest.approx(10.0, abs=1e-9)


def test_slerp_is_stable_for_near_identical_orientations():
    q0 = rotmat_to_quat(np.eye(3))
    q1 = rotmat_to_quat(_rotation_about_z(1e-9))
    out = slerp(q0, q1, np.linspace(0.0, 1.0, 5))
    assert np.all(np.isfinite(out))
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-12)


def test_slerp_sequence_resamples_a_trajectory():
    key_times = np.array([0.0, 1.0, 2.0])
    quats = np.stack([rotmat_to_quat(_rotation_about_z(a)) for a in (0.0, 60.0, 120.0)])

    out = slerp_sequence(key_times, quats, np.array([0.5, 1.5]))

    assert np.allclose(quat_to_rotmat(out[0]), _rotation_about_z(30.0), atol=1e-12)
    assert np.allclose(quat_to_rotmat(out[1]), _rotation_about_z(90.0), atol=1e-12)


def test_slerp_sequence_rejects_mismatched_inputs():
    quats = np.stack([rotmat_to_quat(np.eye(3))] * 3)
    with pytest.raises(ValueError, match="disagree"):
        slerp_sequence(np.array([0.0, 1.0]), quats, np.array([0.5]))


# --------------------------------------------------------------------------
# Integration with the Phase-1 rigid-body fit
# --------------------------------------------------------------------------


def test_kabsch_rotation_converts_to_the_expected_quaternion():
    """README.md §3.2 feeds §3.1: the registration's R becomes a unit quaternion."""
    rng = np.random.default_rng(4)
    source = rng.normal(size=(10, 3))
    r_true = _rotation_about_z(37.0)
    target = source @ r_true.T + np.array([1.0, -2.0, 0.5])

    result = kabsch(source, target)

    assert not result.degenerate
    assert result.R is not None
    quat = rotmat_to_quat(result.R)
    assert np.allclose(quat, rotmat_to_quat(r_true), atol=1e-9)
    assert np.linalg.norm(quat) == pytest.approx(1.0, abs=1e-12)
