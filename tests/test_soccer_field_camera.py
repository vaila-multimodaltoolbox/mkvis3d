"""Pitch camera geometry: homography fit, camera recovery, distortion, plane projection."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("cv2")

from soccer_field_synth import HEIGHT, WIDTH, left_camera, look_at  # noqa: E402

from openbiomech.soccer_field.camera import (  # noqa: E402
    Camera,
    apply_h,
    camera_from_homography,
    fit_homography,
    homography_from_camera,
    in_view,
    project,
)
from openbiomech.soccer_field.kiki49 import load_kiki49  # noqa: E402
from openbiomech.soccer_field.sample import camera_from_plane, project_plane  # noqa: E402


def test_camera_from_homography_recovers_pinhole() -> None:
    cam = left_camera()
    H = homography_from_camera(cam)
    got = camera_from_homography(H, WIDTH, HEIGHT, np.array([[-40.0, 0.0]]))
    assert got is not None
    np.testing.assert_allclose(got.K, cam.K, atol=1e-6)
    np.testing.assert_allclose(got.R, cam.R, atol=1e-9)
    np.testing.assert_allclose(got.t, cam.t, atol=1e-6)


def test_camera_from_homography_rejects_implausible_focal() -> None:
    cam = look_at((-25.0, -55.0, 22.0), (-40.0, 0.0, 0.0), f=100.0)
    assert (
        camera_from_homography(homography_from_camera(cam), WIDTH, HEIGHT, np.zeros((1, 2))) is None
    )


def test_camera_from_plane_agrees_with_homography() -> None:
    cam = left_camera()
    got, disagreement = camera_from_plane(homography_from_camera(cam), WIDTH, HEIGHT)
    assert got is not None
    assert disagreement < 1e-3
    X = load_kiki49().xyz[[34, 35, 38]]  # post tops, flag top: z > 0
    np.testing.assert_allclose(project(X, got)[0], project(X, cam)[0], atol=1e-3)


def test_project_plane_matches_camera_and_marks_points_behind() -> None:
    cam = left_camera()
    H = homography_from_camera(cam)
    xy = np.array([[-40.0, 0.0], [-52.45, 33.95], [-25.0, -80.0]])  # last: behind the camera
    uv, w = project_plane(H, xy, WIDTH, HEIGHT)
    uv_cam, depth = project(np.column_stack([xy, np.zeros(3)]), cam)
    np.testing.assert_allclose(uv, uv_cam, atol=1e-6)
    np.testing.assert_array_equal(w > 0, depth > 0)
    assert depth[2] < 0


def test_distorted_projection_matches_closed_form() -> None:
    k1, k2 = -0.12, 0.03
    cam0 = left_camera()
    cam = Camera(cam0.K, cam0.R, cam0.t, np.array([k1, k2, 0.0, 0.0, 0.0]))
    X = load_kiki49().xyz[:13]
    Xc = X @ cam.R.T + cam.t
    xn = Xc[:, :2] / Xc[:, 2:3]
    r2 = (xn**2).sum(axis=1, keepdims=True)
    xd = xn * (1 + k1 * r2 + k2 * r2**2)
    expected = xd * cam.K[0, 0] + cam.K[:2, 2]
    np.testing.assert_allclose(project(X, cam)[0], expected, atol=1e-6)


def test_fit_homography_least_squares_and_ransac() -> None:
    cam = left_camera()
    H = homography_from_camera(cam)
    xy = load_kiki49().xyz[:13, :2]
    px = apply_h(H, xy)
    exact, mask = fit_homography(xy, px, None)
    assert exact is not None and mask.all()
    np.testing.assert_allclose(apply_h(exact, xy), px, atol=1e-4)

    px_bad = px.copy()
    px_bad[3] += [60.0, -40.0]
    robust, mask = fit_homography(xy, px_bad, 3.0)
    assert robust is not None
    assert not mask[3] and mask.sum() == len(xy) - 1
    np.testing.assert_allclose(apply_h(robust, xy[mask]), px[mask], atol=1e-3)

    assert fit_homography(xy[:3], px[:3])[0] is None


def test_in_view_excludes_behind_and_outside() -> None:
    uv = np.array([[10.0, 10.0], [10.0, 10.0], [-1.0, 5.0], [5.0, HEIGHT], [np.nan, 1.0]])
    depth = np.array([1.0, -1.0, 1.0, 1.0, 1.0])
    np.testing.assert_array_equal(
        in_view(uv, depth, WIDTH, HEIGHT), [True, False, False, False, False]
    )
