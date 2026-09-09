"""Unit tests for Cartesian Bases (s1, s2, sg), relative kinematics, and virtual points."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from openbiomech.kinematic_analysis import (
    add_virtual_points_to_trial,
    build_orthonormal_basis,
    compute_marker_angle,
    compute_two_vector_angle,
    compute_vector_dot_product_angle,
    evaluate_virtual_point_expression,
    relative_segment_kinematics,
)
from openbiomech.marker_trial import MarkerTrial
from openbiomech.trial_io import load_trial


def make_dummy_trial(n_frames: int = 10) -> MarkerTrial:
    """Create a synthetic trial with known marker positions."""
    labels = ("RASI", "LASI", "RKNE", "RANK", "LKNE", "LANK")
    xyz = np.zeros((n_frames, len(labels), 3), dtype=np.float64)

    # RASI and LASI: pelvis markers across frames
    for f in range(n_frames):
        t = f * 0.01
        xyz[f, 0] = [0.10, 0.00 + t, 1.00]  # RASI
        xyz[f, 1] = [-0.10, 0.00 + t, 1.00]  # LASI
        xyz[f, 2] = [0.10, 0.00 + t, 0.50]  # RKNE (thigh distal)
        xyz[f, 3] = [0.10, 0.00 + t, 0.05]  # RANK (shank distal)
        xyz[f, 4] = [-0.10, 0.00 + t, 0.50]  # LKNE
        xyz[f, 5] = [-0.10, 0.00 + t, 0.05]  # LANK

    return MarkerTrial(
        labels=labels,
        rate_hz=100.0,
        xyz=xyz,
        residuals=np.zeros((n_frames, len(labels))),
    )


def test_build_orthonormal_basis_properties():
    """Verify that built bases are strictly orthonormal (unit norm, 90 deg, det = +1)."""
    n_frames = 20
    origin = np.tile([0.0, 1.0, 2.0], (n_frames, 1))
    primary = np.tile([0.0, 1.0, 3.0], (n_frames, 1))  # +Z vector
    plane = np.tile([0.0, 2.0, 2.0], (n_frames, 1))  # +Y vector

    bases, valid = build_orthonormal_basis(
        origin, primary, plane, primary_axis="+z", plane_axis="+y"
    )
    assert valid.all()
    assert bases.shape == (n_frames, 3, 3)

    for f in range(n_frames):
        mat = bases[f]
        ex, ey, ez = mat[:, 0], mat[:, 1], mat[:, 2]

        # 1. Unit norm: each versor divided component-by-component by Euclidean norm
        assert np.isclose(np.linalg.norm(ex), 1.0, atol=1e-12)
        assert np.isclose(np.linalg.norm(ey), 1.0, atol=1e-12)
        assert np.isclose(np.linalg.norm(ez), 1.0, atol=1e-12)

        # 2. Mutually perpendicular (90 degrees): dot products == 0
        assert np.isclose(np.dot(ex, ey), 0.0, atol=1e-12)
        assert np.isclose(np.dot(ey, ez), 0.0, atol=1e-12)
        assert np.isclose(np.dot(ez, ex), 0.0, atol=1e-12)

        # 3. Right-handed: det = +1.0
        det = np.linalg.det(mat)
        assert np.isclose(det, 1.0, atol=1e-12)


def test_build_orthonormal_basis_axis_permutations():
    """Test various primary and plane axis combinations (+x, -y, etc.)."""
    origin = np.array([[1.0, 1.0, 1.0]])
    primary = np.array([[3.0, 1.0, 1.0]])  # +X
    plane = np.array([[1.0, 4.0, 1.0]])  # +Y

    bases, valid = build_orthonormal_basis(
        origin, primary, plane, primary_axis="+x", plane_axis="+y"
    )
    assert valid[0]
    mat = bases[0]
    ex, ey, ez = mat[:, 0], mat[:, 1], mat[:, 2]

    assert np.allclose(ex, [1.0, 0.0, 0.0], atol=1e-12)
    assert np.allclose(ey, [0.0, 1.0, 0.0], atol=1e-12)
    assert np.allclose(ez, [0.0, 0.0, 1.0], atol=1e-12)
    assert np.isclose(np.linalg.det(mat), 1.0, atol=1e-12)


def test_relative_segment_kinematics_formula():
    """Verify MR2 = sg @ s1.T and MR = (MR2 @ s2) @ sg.T."""
    n_frames = 5

    # Known pure rotation around Z by 45 degrees for s2 relative to s1
    rot_45z = Rotation.from_euler("z", 45, degrees=True).as_matrix()

    s1 = np.tile(np.eye(3), (n_frames, 1, 1))
    s2 = np.tile(rot_45z, (n_frames, 1, 1))

    # Case 1: sg = Identity
    res_id = relative_segment_kinematics(s1, s2, sg=None, sequence="zxy")
    assert np.allclose(res_id["MR"], s2, atol=1e-12)
    assert np.isclose(res_id["euler"][0, 0], 45.0, atol=1e-6)
    assert np.isclose(res_id["euler"][0, 1], 0.0, atol=1e-6)
    assert np.isclose(res_id["euler"][0, 2], 0.0, atol=1e-6)

    # Case 2: sg is a rotated laboratory frame (e.g. 90 deg around X)
    rot_sg = Rotation.from_euler("x", 90, degrees=True).as_matrix()
    sg_stack = np.tile(rot_sg, (n_frames, 1, 1))

    res_sg = relative_segment_kinematics(s1, s2, sg=sg_stack, sequence="zxy")
    expected_mr2 = sg_stack @ np.swapaxes(s1, -1, -2)
    expected_mr = (expected_mr2 @ s2) @ np.swapaxes(sg_stack, -1, -2)

    assert np.allclose(res_sg["MR2"], expected_mr2, atol=1e-12)
    assert np.allclose(res_sg["MR"], expected_mr, atol=1e-12)


def test_evaluate_virtual_point_expression():
    """Test formula evaluation for virtual landmarks."""
    trial = make_dummy_trial(n_frames=10)

    # Midpoint of RASI and LASI: should be at x=0.0
    mid_pelvis = evaluate_virtual_point_expression(trial, "(p['RASI'] + p['LASI']) / 2")
    assert mid_pelvis.shape == (10, 3)
    assert np.allclose(mid_pelvis[:, 0], 0.0, atol=1e-12)
    assert np.allclose(mid_pelvis[:, 2], 1.0, atol=1e-12)

    # Vector difference
    diff = evaluate_virtual_point_expression(trial, "p['RASI'] - p['LASI']")
    assert np.allclose(diff[:, 0], 0.20, atol=1e-12)


def test_add_virtual_points_to_trial():
    """Test adding virtual points and building bases from them."""
    trial = make_dummy_trial(n_frames=10)
    vp_list = [
        {"name": "MID_ASIS", "expression": "(p['RASI'] + p['LASI']) / 2"},
        {"name": "THIGH_VEC", "expression": "p['RKNE'] - p['RASI']"},
    ]

    extended_trial = add_virtual_points_to_trial(trial, vp_list)
    assert "MID_ASIS" in extended_trial.labels
    assert "THIGH_VEC" in extended_trial.labels
    assert extended_trial.xyz.shape == (10, len(trial.labels) + 2, 3)

    # Use virtual point as origin
    origin = extended_trial.marker("MID_ASIS")
    prim = extended_trial.marker("RKNE")
    plane = extended_trial.marker("LASI")

    bases, valid = build_orthonormal_basis(origin, prim, plane)
    assert valid.all()
    assert np.isclose(np.linalg.det(bases[0]), 1.0, atol=1e-12)


def test_real_trial_kinematics_workflow():
    """Test full kinematics pipeline on golden fixture trial."""
    c3d_path = Path("data/rec3d_sample_m.c3d")
    if not c3d_path.exists():
        return

    trial = load_trial(c3d_path)
    p1 = trial.labels[0]
    p2 = trial.labels[1]
    p3 = trial.labels[2]
    p4 = trial.labels[3]

    extended = add_virtual_points_to_trial(
        trial, [{"name": "V_MID", "expression": f"(p['{p1}'] + p['{p2}']) / 2"}]
    )
    assert "V_MID" in extended.labels

    s1_bases, s1_valid = build_orthonormal_basis(
        extended.marker(p1), extended.marker(p2), extended.marker(p3)
    )

    s2_bases, s2_valid = build_orthonormal_basis(
        extended.marker("V_MID"), extended.marker(p3), extended.marker(p4)
    )

    kin = relative_segment_kinematics(s1_bases, s2_bases, sequence="zxy")
    assert kin["MR"].shape == (trial.n_frames, 3, 3)
    assert kin["euler"].shape == (trial.n_frames, 3)
    assert kin["quaternions"].shape == (trial.n_frames, 4)

    valid_mask = kin["valid"]
    if valid_mask.any():
        quat_norms = np.linalg.norm(kin["quaternions"][valid_mask], axis=1)
        assert np.allclose(quat_norms, 1.0, atol=1e-10)


def test_gui_kinematics_bases_endpoints():
    """Test /api/analyze/kinematics_bases and /api/analyze/evaluate_point endpoints."""
    import json
    from http.client import HTTPConnection
    from threading import Thread

    from openbiomech.viewer import create_server, trial_payload

    trial = make_dummy_trial(n_frames=10)
    server, url = create_server(0, trial_payload(trial, "dummy"))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    auth_token = url.split("#")[1]

    try:
        # 1. Test /api/analyze/evaluate_point
        payload_eval = {
            "trial": trial_payload(trial, "dummy"),
            "name": "MID_ASIS",
            "expression": "(p['RASI'] + p['LASI']) / 2",
        }
        connection.request(
            "POST",
            "/api/analyze/evaluate_point",
            body=json.dumps(payload_eval).encode(),
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
            },
        )
        resp_eval = connection.getresponse()
        assert resp_eval.status == 200
        res_eval = json.loads(resp_eval.read())
        assert res_eval["name"] == "MID_ASIS"
        assert len(res_eval["coords"]) == 10
        assert np.isclose(res_eval["coords"][0][0], 0.0)

        # 2. Test /api/analyze/kinematics_bases
        payload_kin = {
            "trial": trial_payload(trial, "dummy"),
            "virtual_points": [{"name": "MID_ASIS", "expression": "(p['RASI'] + p['LASI']) / 2"}],
            "s1": {
                "origin": "MID_ASIS",
                "primary_pt": "RKNE",
                "plane_pt": "LASI",
                "primary_axis": "+z",
                "plane_axis": "+y",
            },
            "s2": {
                "origin": "RKNE",
                "primary_pt": "RANK",
                "plane_pt": "MID_ASIS",
                "primary_axis": "+z",
                "plane_axis": "+y",
            },
            "sequence": "zxy",
        }
        connection.request(
            "POST",
            "/api/analyze/kinematics_bases",
            body=json.dumps(payload_kin).encode(),
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
            },
        )
        resp_kin = connection.getresponse()
        assert resp_kin.status == 200
        res_kin = json.loads(resp_kin.read())
        assert "MR" in res_kin
        assert "MR2" in res_kin
        assert "euler" in res_kin
        assert "quaternions" in res_kin
        assert len(res_kin["euler"]) == 10
        assert len(res_kin["quaternions"]) == 10
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_compute_vector_dot_product_angle_basic():
    """Verify dot product angle calculations for canonical orthogonal and collinear vectors."""
    # 1. Orthogonal: 90 degrees
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0])
    assert np.isclose(compute_vector_dot_product_angle(u, v), 90.0, atol=1e-12)
    assert np.isclose(compute_vector_dot_product_angle(u, v, degrees=False), np.pi / 2, atol=1e-12)

    # 2. Parallel: 0 degrees
    u = np.array([2.5, 0.0, 0.0])
    v = np.array([10.0, 0.0, 0.0])
    assert np.isclose(compute_vector_dot_product_angle(u, v), 0.0, atol=1e-12)

    # 3. Anti-parallel: 180 degrees
    u = np.array([0.0, 3.0, 0.0])
    v = np.array([0.0, -5.0, 0.0])
    assert np.isclose(compute_vector_dot_product_angle(u, v), 180.0, atol=1e-12)

    # 4. 45 degrees
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([1.0, 1.0, 0.0])
    assert np.isclose(compute_vector_dot_product_angle(u, v), 45.0, atol=1e-12)

    # 5. 60 degrees: u = [1, 0, 0], v = [0.5, sqrt(3)/2, 0]
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([0.5, np.sqrt(3) / 2.0, 0.0])
    assert np.isclose(compute_vector_dot_product_angle(u, v), 60.0, atol=1e-12)


def test_compute_vector_dot_product_angle_edge_cases():
    """Verify handling of degenerate vectors, NaNs, and floating point overshoots."""
    # Zero vector -> NaN
    u = np.array([0.0, 0.0, 0.0])
    v = np.array([1.0, 2.0, 3.0])
    assert np.isnan(compute_vector_dot_product_angle(u, v))

    # NaN vector -> NaN
    u = np.array([np.nan, 1.0, 2.0])
    v = np.array([1.0, 1.0, 1.0])
    assert np.isnan(compute_vector_dot_product_angle(u, v))

    # Trajectory batch (N, 3)
    n = 20
    traj_u = np.tile([1.0, 0.0, 0.0], (n, 1))
    traj_v = np.tile([0.0, 1.0, 0.0], (n, 1))
    angles = compute_vector_dot_product_angle(traj_u, traj_v)
    assert angles.shape == (n,)
    assert np.allclose(angles, 90.0, atol=1e-12)


def test_compute_marker_angle_joint():
    """Verify 3-marker joint angle (Vertex B between A and C)."""
    trial = make_dummy_trial(n_frames=5)
    # RASI=[0.1, t, 1.0], RKNE=[0.1, t, 0.5], RANK=[0.1, t, 0.05]
    # At vertex RKNE:
    # u = RASI - RKNE = [0, 0, 0.5] (points straight UP along +Z)
    # v = RANK - RKNE = [0, 0, -0.45] (points straight DOWN along -Z)
    # Expected angle = 180 degrees (straight extended limb)
    angles = compute_marker_angle(trial, "RASI", "RKNE", "RANK")
    assert len(angles) == 5
    assert np.allclose(angles, 180.0, atol=1e-12)


def test_compute_two_vector_angle_segments():
    """Verify 4-marker angle between two independent segment vectors."""
    trial = make_dummy_trial(n_frames=5)
    # V1: LASI -> RASI = [0.2, 0, 0] (lateral X)
    # V2: RKNE -> RASI = [0, 0, 0.5] (vertical Z)
    # Orthogonal -> 90 degrees
    angles = compute_two_vector_angle(trial, "LASI", "RASI", "RKNE", "RASI")
    assert len(angles) == 5
    assert np.allclose(angles, 90.0, atol=1e-12)


def test_manual_coordinate_virtual_point():
    """Verify manual coordinate point creation and evaluate_virtual_point_expression."""
    trial = make_dummy_trial(n_frames=10)

    # String list literal
    coords_str = evaluate_virtual_point_expression(trial, "[0.25, -0.75, 1.50]")
    assert coords_str.shape == (10, 3)
    assert np.allclose(coords_str[0], [0.25, -0.75, 1.50])
    assert np.allclose(coords_str[9], [0.25, -0.75, 1.50])

    # Direct list
    coords_list = evaluate_virtual_point_expression(trial, [0.10, 0.20, 0.30])
    assert coords_list.shape == (10, 3)
    assert np.allclose(coords_list[0], [0.10, 0.20, 0.30])

    # Adding manual virtual point to trial
    vp_spec = [{"name": "CALIB_ORIGIN", "expression": "[0.0, 0.0, 0.0]"}]
    augmented = add_virtual_points_to_trial(trial, vp_spec)
    assert "CALIB_ORIGIN" in augmented.labels
    calib = augmented.marker("CALIB_ORIGIN")
    assert calib.shape == (10, 3)
    assert np.allclose(calib, 0.0)
