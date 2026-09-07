"""Independent physical balances for the continuation's end-to-end path."""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.spatial.transform import Rotation

from openbiomech.inverse_dynamics.chain import SegmentDynamics, inverse_dynamics_chain
from openbiomech.inverse_dynamics.force_plate import global_plate_wrench, plate_frame
from openbiomech.inverse_dynamics.newton_euler import GRAVITY
from openbiomech.model.bsp import global_inertia_tensor, inertia_tensor

# Continuation order yields identity; official C3D order is 0,3,2,1.
CORNERS = np.array([[0.5, 0.25, 0], [0.5, -0.25, 0], [-0.5, -0.25, 0], [-0.5, 0.25, 0]])


@pytest.mark.parametrize(
    "segment,radii",
    [
        ("thigh", [0.329, 0.329, 0.149]),
        ("shank", [0.255, 0.249, 0.103]),
        ("foot", [0.257, 0.245, 0.124]),
    ],
)
def test_inertia_matches_requested_profile_and_length_squared(segment, radii):
    expected = np.diag([2 * (r * 0.4) ** 2 for r in radii])
    assert_allclose(inertia_tensor(segment, 2, 0.4), expected, atol=1e-15)
    assert_allclose(inertia_tensor(segment, 4, 0.8), 8 * expected, atol=1e-15)
    assert inertia_tensor(segment, 2, 0.4).dtype == np.float64


def test_rotated_inertia_swaps_principal_axes_and_preserves_eigenvalues():
    local = np.diag([1.0, 2.0, 3.0])
    R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    actual = global_inertia_tensor(local, np.stack([np.eye(3), R]))
    assert_allclose(actual[1], np.diag([2.0, 1.0, 3.0]))
    assert_allclose(np.linalg.eigvalsh(actual), [[1, 2, 3], [1, 2, 3]])


@pytest.mark.parametrize("mass,length", [(0, 1), (-1, 1), (1, 0), (np.nan, 1), (1, np.inf)])
def test_inertia_rejects_invalid_physical_inputs(mass, length):
    with pytest.raises(ValueError):
        inertia_tensor("thigh", mass, length)


def test_inertia_does_not_invent_pelvis_table_or_accept_reflections():
    with pytest.raises(ValueError, match="radii"):
        inertia_tensor("pelvis", 10, 0.2)
    with pytest.raises(ValueError, match="right-handed"):
        global_inertia_tensor(np.eye(3), np.diag([1, 1, -1]))
    with pytest.raises(ValueError, match="physical"):
        global_inertia_tensor(np.diag([1, 1, 4]), np.eye(3))


def test_cop_translation_rotation_and_free_moment_known_by_hand():
    # Local COP=(.1,.05,0), F=(10,20,200), free Mz=7.
    # Surface M = COP x F + free = (10,-20,8.5).
    R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    corners = CORNERS @ R.T + [2, 3, 0.4]
    wrench = global_plate_wrench(np.array([10, 20, 200]), np.array([10, -20, 8.5]), corners)
    assert_allclose(wrench["cop"], [1.95, 3.1, 0.4])
    assert_allclose(wrench["force"], [-20, 10, 200])
    assert_allclose(wrench["moment"], [0, 0, 7], atol=1e-12)
    assert wrench["contact"]


def test_c3d_corner_layout_and_convention_are_explicit():
    official = CORNERS[[0, 3, 2, 1]]
    origin, R = plate_frame(official.T, convention="c3d")
    assert_allclose(origin, 0)
    assert_allclose(R, np.eye(3))
    _, other = plate_frame(official)
    assert_allclose(other[:, 2], [0, 0, -1])


def test_strict_contact_threshold_and_tilted_plate_use_local_normal():
    R = Rotation.from_euler("y", 90, degrees=True).as_matrix()
    force = np.array([[0, 0, 0], [0, 0, 15], [0, 0, 16], [0, 0, -100]])
    wrench = global_plate_wrench(force, np.zeros((4, 3)), CORNERS @ R.T + [4, 5, 6])
    assert_allclose(wrench["contact"], [False, False, True, False])
    assert_allclose(wrench["cop"][[0, 1, 3]], 0)
    assert_allclose(wrench["force"][2], [16, 0, 0], atol=1e-12)
    assert_allclose(wrench["cop"][2], [4, 5, 6])


@pytest.mark.parametrize(
    "corners", [np.zeros((4, 3)), CORNERS + np.diag([0, 0, 0.1, 0])[:, :3], np.ones((3, 3))]
)
def test_bad_plate_geometry_is_rejected(corners):
    with pytest.raises(ValueError):
        plate_frame(corners)


def make_chain(n=8):
    zero = np.zeros((n, 3))
    segments = []
    for i, (name, mass, length) in enumerate(
        [("foot", 1.0, 0.2), ("shank", 3.0, 0.4), ("thigh", 7.0, 0.4), ("pelvis", 9.0, 0.2)]
    ):
        distal = np.tile([0.1 * i, 0, 0.3 * i], (n, 1))
        proximal = np.tile([0.1 * (i + 1), 0, 0.3 * (i + 1)], (n, 1))
        # Explicit synthetic pelvis tensor, not an anthropometric table.
        inertia = (
            np.diag([0.1, 0.12, 0.15]) if name == "pelvis" else inertia_tensor(name, mass, length)
        )
        segments.append(
            SegmentDynamics(
                name,
                mass,
                inertia,
                np.tile(np.eye(3), (n, 1, 1)),
                (distal + proximal) / 2,
                proximal,
                distal,
                zero.copy(),
                zero.copy(),
                zero.copy(),
            )
        )
    return segments


def test_static_four_segment_chain_matches_whole_subsystem_equilibrium():
    segments = make_chain()
    force = np.tile([0, 0, 20 * 9.80665], (8, 1))
    surface_moment = np.tile([0, -0.08 * force[0, 2], 3.0], (8, 1))
    plate = global_plate_wrench(force, surface_moment, CORNERS)
    result = inverse_dynamics_chain(segments, plate["force"], plate["moment"], plate["cop"])
    for i, segment in enumerate(segments):
        expected_force = -sum(s.mass_kg for s in segments[: i + 1]) * GRAVITY - force
        assert_allclose(result[segment.name]["force_proximal"], expected_force, atol=1e-12)
        # Whole distal subsystem moment equilibrium about the proximal joint.
        expected_moment = -np.cross(plate["cop"] - segment.proximal, force) - plate["moment"]
        for s in segments[: i + 1]:
            expected_moment -= np.cross(s.com - segment.proximal, s.mass_kg * GRAVITY)
        assert_allclose(result[segment.name]["moment_proximal"], expected_moment, atol=1e-12)
    assert_allclose(result["pelvis"]["force_proximal"], 0, atol=1e-12)


def test_dynamic_chain_conserves_total_linear_and_angular_momentum():
    segments = make_chain()
    t = np.linspace(0, 0.7, 8)
    R = Rotation.from_rotvec(np.column_stack([t * 0, 0.5 * t**2, t * 0])).as_matrix()
    omega = np.column_stack([t * 0, t, t * 0])
    alpha = np.tile([0, 1.0, 0], (8, 1))
    for s in segments:
        s.rotation = R
        for field in ("com", "proximal", "distal"):
            setattr(s, field, np.einsum("nij,nj->ni", R, getattr(s, field)))
        s.angular_velocity = omega
        s.angular_acceleration = alpha
        s.com_acceleration = np.cross(alpha, s.com) + np.cross(omega, np.cross(omega, s.com))
    force = np.tile([10, 20, 300.0], (8, 1))
    cop = np.tile([0.08, 0.04, 0], (8, 1))
    free = np.tile([0, 0, 5.0], (8, 1))
    plate = global_plate_wrench(force, np.cross(cop, force) + free, CORNERS)
    out = inverse_dynamics_chain(segments, plate["force"], plate["moment"], plate["cop"])["pelvis"]
    total_linear = sum(s.mass_kg * s.com_acceleration for s in segments)
    total_weight = sum(s.mass_kg for s in segments) * GRAVITY
    assert_allclose(out["force_proximal"] + force + total_weight, total_linear, atol=1e-12)
    angular_rate = np.zeros((8, 3))
    gravity_torque = np.zeros((8, 3))
    for s in segments:
        inertia = R @ s.inertia_com @ R.swapaxes(1, 2)
        angular_rate += np.einsum("nij,nj->ni", inertia, alpha)
        angular_rate += np.cross(omega, np.einsum("nij,nj->ni", inertia, omega))
        angular_rate += np.cross(s.com, s.mass_kg * s.com_acceleration)
        gravity_torque += np.cross(s.com, s.mass_kg * GRAVITY)
    external = out["moment_proximal"] + np.cross(segments[-1].proximal, out["force_proximal"])
    external += np.cross(cop, force) + free + gravity_torque
    assert_allclose(external, angular_rate, atol=1e-12)


def test_free_falling_chain_requires_no_joint_loads():
    segments = make_chain()
    for s in segments:
        s.com_acceleration[:] = GRAVITY
    zero = np.zeros((8, 3))
    result = inverse_dynamics_chain(segments, zero, zero, zero)
    for loads in result.values():
        assert_allclose(loads["force_proximal"], 0)
        assert_allclose(loads["moment_proximal"], 0)


def test_chain_rejects_disconnected_joints_and_unsynchronized_samples():
    segments = make_chain()
    zero = np.zeros((8, 3))
    segments[1].distal += 0.1
    with pytest.raises(ValueError, match="coincide"):
        inverse_dynamics_chain(segments, zero, zero, zero)
    with pytest.raises(ValueError, match="shape"):
        inverse_dynamics_chain(make_chain(), zero[:4], zero, zero)
