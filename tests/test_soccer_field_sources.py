"""Source converters: line support, pitch32 clicks, SoccerNet lines, splits and dedupe."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")

from soccer_field_synth import (  # noqa: E402
    HEIGHT,
    WIDTH,
    left_camera,
    projected_kiki,
    render_pitch,
)

from openbiomech.soccer_field.build_kiki49 import check_leakage, dedupe  # noqa: E402
from openbiomech.soccer_field.camera import homography_from_camera, project  # noqa: E402
from openbiomech.soccer_field.kiki49 import (  # noqa: E402
    ARC_POINTS,
    LEGACY_GOAL_Y_POINTS_XY,
    N_KPT,
    ground_lines,
    load_kiki49,
)
from openbiomech.soccer_field.line_support import line_distance_map, support_score  # noqa: E402
from openbiomech.soccer_field.sample import (  # noqa: E402
    ORIGIN_ANNOTATED,
    ORIGIN_CAMERA,
    ORIGIN_PLANE,
    Reject,
    Sample,
    project_plane,
)
from openbiomech.soccer_field.soccernet_lines import (  # noqa: E402
    CIRCLE_CROSSINGS,
    GROUND_LINES,
    POSTS,
    parse_annotation,
)
from openbiomech.soccer_field.sources import Options, hashed_split  # noqa: E402
from openbiomech.soccer_field.sources.clicks import (
    ARC_TOL_M,
    camera_agreement,
    clicks_to_sample,
)  # noqa: E402
from openbiomech.soccer_field.sources.homography import metric_homography  # noqa: E402

OPTS = Options()


def _legacy_uv(cam, k: int) -> np.ndarray:
    return project(np.array([[*LEGACY_GOAL_Y_POINTS_XY[k], 0.0]]), cam)[0][0]


def _clicks(cam) -> np.ndarray:
    uv, ok = projected_kiki(cam)
    clicks = np.zeros((32, 3))
    vis = ok[:32]
    clicks[vis, :2], clicks[vis, 2] = uv[:32][vis], 1.0
    return clicks


def test_line_support_aligned_vs_shifted() -> None:
    cam = left_camera()
    H = homography_from_camera(cam)

    def fn(X: np.ndarray):
        return project_plane(H, X[:, :2], WIDTH, HEIGHT)

    assert support_score(line_distance_map(render_pitch(cam)), fn) > 0.95
    assert support_score(line_distance_map(render_pitch(cam, shift_px=15.0)), fn) < 0.1

    def outside(X: np.ndarray):
        return np.full((len(X), 2), -5.0), np.ones(len(X))

    assert np.isnan(support_score(np.zeros((HEIGHT, WIDTH), np.float32), outside))


def test_camera_agreement_drops_legacy_arc_click() -> None:
    cam = left_camera()
    clicks = _clicks(cam)
    clicks[10, :2] = _legacy_uv(cam, 10)
    ann = np.zeros((N_KPT, 3))
    ann[:32] = clicks
    agreement, cleaned, n_legacy = camera_agreement(ann, cam, WIDTH)
    assert n_legacy == 1 and not cleaned[10].any()
    assert agreement == pytest.approx(0.0, abs=1e-6)


def test_clicks_upgrade_through_click_homography() -> None:
    cam = left_camera()
    img = render_pitch(cam)
    uv, ok = projected_kiki(cam)
    clicks = _clicks(cam)
    clicks[11, :2] = _legacy_uv(cam, 11)  # old pitch32 meaning of point 11
    got = clicks_to_sample("t", "u", "train", "g", clicks, img, Path("x.jpg"), OPTS)
    assert isinstance(got, Sample), got
    assert got.stats["legacy_arc"] == 1.0
    assert got.stats["click_residual"] < 1e-3
    assert got.origin[11] == ORIGIN_PLANE
    np.testing.assert_allclose(got.kps[11, :2], uv[11], atol=1e-3)
    clicked = np.flatnonzero(clicks[:, 2] > 0)
    clicked = clicked[clicked != 11]
    assert (got.origin[clicked] == ORIGIN_ANNOTATED).all()
    assert got.aux3d and (got.kps[ok, 2] == 2).all() and not got.kps[~ok].any()
    np.testing.assert_allclose(got.kps[ok, :2], uv[ok], atol=0.05)


def test_clicks_prefer_an_agreeing_tracked_camera() -> None:
    cam = left_camera()
    uv, ok = projected_kiki(cam)
    clicks = _clicks(cam)
    got = clicks_to_sample(
        "t", "u", "train", "g", clicks, render_pitch(cam), Path("x.jpg"), OPTS, cam
    )
    assert isinstance(got, Sample) and got.H is None and got.camera is cam
    assert (got.origin[32:][ok[32:]] == ORIGIN_CAMERA).all()
    np.testing.assert_allclose(got.kps[ok, :2], uv[ok], atol=1e-6)


def test_clicks_reject_without_line_support() -> None:
    cam = left_camera()
    blank = np.full((HEIGHT, WIDTH, 3), (40, 120, 40), dtype=np.uint8)
    got = clicks_to_sample("t", "u", "train", "g", _clicks(cam), blank, Path("x.jpg"), OPTS)
    assert isinstance(got, Reject) and got.reason == "line_support"


def _soccernet_json(cam) -> dict[str, list[dict[str, float]]]:
    """Normalized polylines of what ``cam`` sees, in calibration-2023 layout."""

    def poly(X: np.ndarray) -> list[dict[str, float]]:
        uv, depth = project(X, cam)
        keep = (
            (depth > 0)
            & (uv[:, 0] >= 0)
            & (uv[:, 0] < WIDTH)
            & (uv[:, 1] >= 0)
            & (uv[:, 1] < HEIGHT)
        )
        return [{"x": u / WIDTH, "y": v / HEIGHT} for u, v in uv[keep]]

    def seg(a, b, n: int = 40) -> np.ndarray:
        return np.linspace(a, b, n)

    ann = {n: poly(seg([*a, 0.0], [*b, 0.0])) for n, (a, b) in GROUND_LINES.items()}
    ann["Circle left"] = poly(ground_lines(0.1)[12])  # the left penalty arc
    xyz = load_kiki49().xyz
    for name, (base, top) in POSTS.items():
        ann[name] = poly(seg(xyz[base], xyz[top]))
    ann["Goal left crossbar"] = poly(seg(xyz[34], xyz[35]))
    return {k: v for k, v in ann.items() if len(v) >= 2}


def test_soccernet_lines_to_kiki_points() -> None:
    cam = left_camera()
    uv, _ = projected_kiki(cam)
    lab = parse_annotation(_soccernet_json(cam), WIDTH, HEIGHT)
    assert lab.H is not None
    np.testing.assert_allclose(lab.H, homography_from_camera(cam), rtol=1e-5, atol=1e-8)
    got = np.flatnonzero(lab.annotated[:, 2] > 0)
    far, near = CIRCLE_CROSSINGS[("Circle left", "Big rect. left main")]
    assert {1, 2, 3, 4, 6, 7, 9, 12, far, near, 32, 33, 34, 35} <= set(got.tolist())
    np.testing.assert_allclose(lab.annotated[got, :2], uv[got], atol=0.05)
    assert lab.stats["post_named_err"] < 0.05 < lab.stats["post_swap_err"]
    assert np.median(lab.residual_px) < 0.05


def test_wc14_metric_homography_convention() -> None:
    """Raw WC14/TS-WorldCup H maps pixels to the 114.83 x 74.37 yd template (y down)."""
    cam = left_camera()
    H_metric = homography_from_camera(cam)
    T = np.array(
        [[114.83 / 104.9, 0.0, 114.83 / 2], [0.0, -74.37 / 67.9, 74.37 / 2], [0.0, 0.0, 1.0]]
    )
    H_raw = T @ np.linalg.inv(H_metric)
    np.testing.assert_allclose(metric_homography(H_raw), H_metric, rtol=1e-9, atol=1e-9)


def test_hashed_split_is_deterministic_and_balanced() -> None:
    groups = [f"clip:{i}" for i in range(2000)]
    splits = [hashed_split(g) for g in groups]
    assert splits == [hashed_split(g) for g in groups]
    frac = {s: splits.count(s) / len(splits) for s in ("train", "val", "test")}
    assert frac["train"] == pytest.approx(0.70, abs=0.04)
    assert frac["val"] == pytest.approx(0.15, abs=0.03)
    assert frac["test"] == pytest.approx(0.15, abs=0.03)


def _sample(source: str, uid: str, split: str, group: str, image: str) -> Sample:
    return Sample(
        source, uid, split, group, WIDTH, HEIGHT, np.zeros((N_KPT, 3)), np.zeros(N_KPT), Path(image)
    )


def test_dedupe_keeps_highest_priority_source() -> None:
    items = [
        (_sample("wc14", "a", "train", "w", "/x/a.jpg"), "h1"),
        (_sample("martinjolif", "b", "train", "m", "/x/b.jpg"), "h1"),  # same bytes
        (_sample("soccernet", "c", "train", "s", "/x/a.jpg"), "h2"),  # same path as wc14
        (_sample("fifa_video", "d", "train", "f", "/x/d.jpg"), "h3"),
    ]
    kept, dropped = dedupe(items)
    assert [s.source for s in kept] == ["martinjolif", "soccernet", "fifa_video"]
    assert dropped == {"wc14": 1}


def test_check_leakage_rejects_group_in_two_splits() -> None:
    ok = [_sample("s", "a", "train", "g1", "a"), _sample("s", "b", "val", "g2", "b")]
    check_leakage(ok)
    with pytest.raises(SystemExit):
        check_leakage([*ok, _sample("s", "c", "test", "g1", "c")])


def test_arc_points_differ_from_legacy_by_more_than_the_tolerance() -> None:
    xyz = load_kiki49().xyz
    for k in ARC_POINTS:
        assert np.hypot(*(xyz[k, :2] - LEGACY_GOAL_Y_POINTS_XY[k])) > 1.5 * ARC_TOL_M
