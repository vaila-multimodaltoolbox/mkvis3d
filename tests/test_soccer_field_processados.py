"""vailá goal-point clicks (processados) -> camera -> complete kiki49 labels."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")

from soccer_field_synth import look_at, projected_kiki, render_pitch  # noqa: E402

from openbiomech.soccer_field.kiki49 import N_KPT, load_kiki49  # noqa: E402
from openbiomech.soccer_field.sample import Reject, Sample  # noqa: E402
from openbiomech.soccer_field.sources import Options  # noqa: E402
from openbiomech.soccer_field.sources.processados import (  # noqa: E402
    FLAG_LEFT_SIDE,
    FLAG_RIGHT_SIDE,
    N_CLICKS,
    RIGHT_GOAL,
    camera_centre,
    clicks_to_goal_sample,
    right_goal_mapping,
    rot180,
)


def test_rot180_is_a_half_turn_involution() -> None:
    idx = rot180()
    np.testing.assert_array_equal(idx[idx], np.arange(N_KPT))
    xyz = load_kiki49().xyz
    np.testing.assert_allclose(xyz[idx], xyz * [-1.0, -1.0, 1.0])


def goal_clicks(cam, to_kiki: dict[int, int]) -> np.ndarray:
    uv, ok = projected_kiki(cam)
    clicks = np.zeros((N_CLICKS, 3))
    for c, k in to_kiki.items():
        assert ok[k], f"click {c} (kiki {k}) out of view"
        clicks[c] = [*uv[k], 2.0]
    return clicks


# Main-stand cameras (y < 0) on each goal; "left" is seen from the pitch facing the goal,
# so the corner nearest the camera lies beyond the right post at the right goal and
# beyond the left post at the left one.
@pytest.mark.parametrize(
    ("centre", "target", "turned", "flag"),
    [
        ((25.0, -55.0, 22.0), (42.0, -12.0, 0.0), False, FLAG_RIGHT_SIDE),
        ((-25.0, -55.0, 22.0), (-42.0, -12.0, 0.0), True, FLAG_LEFT_SIDE),
    ],
)
def test_goal_clicks_recover_camera_and_label_the_whole_field(
    centre, target, turned: bool, flag: dict[int, int]
) -> None:
    cam = look_at(centre, target, f=1000.0)
    turn = rot180() if turned else np.arange(N_KPT)
    to_kiki = {c: int(turn[k]) for c, k in (RIGHT_GOAL | flag).items()}
    clicks = goal_clicks(cam, to_kiki)
    img = render_pitch(cam)

    assert right_goal_mapping(clicks) == RIGHT_GOAL | flag
    s = clicks_to_goal_sample("u", "train", "g", clicks, img, Path("x.png"), Options())
    assert isinstance(s, Sample), s
    assert s.camera is not None
    np.testing.assert_allclose(camera_centre(s.camera), centre, atol=0.5)

    uv, ok = projected_kiki(cam)
    vis = s.kps[:, 2] > 0
    np.testing.assert_array_equal(vis, ok)
    np.testing.assert_allclose(s.kps[vis, :2], uv[vis], atol=2.0)
    for c, k in to_kiki.items():
        np.testing.assert_allclose(s.kps[k, :2], clicks[c, :2])


def test_goal_clicks_without_field_markings_are_rejected() -> None:
    cam = look_at((25.0, -55.0, 22.0), (42.0, -12.0, 0.0), f=1000.0)
    clicks = goal_clicks(cam, RIGHT_GOAL | FLAG_RIGHT_SIDE)
    blank = render_pitch(cam)
    blank[:] = (40, 120, 40)
    r = clicks_to_goal_sample("u", "train", "g", clicks, blank, Path("x.png"), Options())
    assert isinstance(r, Reject) and r.reason == "line_support"
