"""Geometry lock for Kiki-49 centre circle + penalty arcs (vailá Law 1 parity)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from openbiomech.c3d_io import read_c3d_native

PENALTY_ARC_RADIUS_M = 9.15
C3D_PATH = Path(__file__).parent.parent / "data" / "soccerfield_kiki_custom.c3d"


def _penalty_arc_geometry(
    points: dict[str, tuple[float, float, float]],
    side: str,
) -> dict[str, Any] | None:
    """Inline mirror of vailá drawsportsfields.penalty_arc_geometry (radians)."""
    spot_key = f"{side}_penalty_spot"
    if spot_key not in points:
        return None
    spot = points[spot_key]
    center = (float(spot[0]), float(spot[1]))

    intersection_keys = (
        f"{side}_penalty_arc_left_intersection",
        f"{side}_penalty_arc_right_intersection",
    )
    line_x: float | None = None
    for key in (
        *intersection_keys,
        f"{side}_penalty_area_top_left",
        f"{side}_pen_box_bottom_inner",
        f"{side}_pen_box_top_inner",
    ):
        if key in points:
            line_x = float(points[key][0])
            break
    if line_x is None:
        return None

    radius: float | None = None
    for key in intersection_keys:
        if key in points:
            radius = math.hypot(
                float(points[key][0]) - center[0],
                float(points[key][1]) - center[1],
            )
            break
    if radius is None and "center_field" in points:
        for key in ("center_circle_top_intersection", "center_circle_top"):
            if key in points:
                radius = abs(float(points[key][1]) - float(points["center_field"][1]))
                break
    if radius is None or radius <= 0.0:
        radius = PENALTY_ARC_RADIUS_M

    dx = abs(line_x - center[0])
    if not 0.0 < dx < radius:
        return None
    theta = math.acos(dx / radius)
    if side == "left":
        return {"center": center, "radius": radius, "theta1": -theta, "theta2": theta}
    return {
        "center": center,
        "radius": radius,
        "theta1": math.pi - theta,
        "theta2": math.pi + theta,
    }


def _arc_endpoint(geom: dict[str, Any], ang: float) -> tuple[float, float]:
    return (
        geom["center"][0] + geom["radius"] * math.cos(ang),
        geom["center"][1] + geom["radius"] * math.sin(ang),
    )


@pytest.fixture(scope="module")
def kiki_points() -> dict[str, tuple[float, float, float]]:
    if not C3D_PATH.is_file():
        pytest.skip(f"missing fixture {C3D_PATH}")
    trial = read_c3d_native(C3D_PATH)
    return {
        lab: (float(trial.xyz[0, i, 0]), float(trial.xyz[0, i, 1]), float(trial.xyz[0, i, 2]))
        for i, lab in enumerate(trial.labels)
    }


def test_center_circle_radius_uses_y_only(
    kiki_points: dict[str, tuple[float, float, float]],
) -> None:
    center = kiki_points["center_field"]
    top = kiki_points["center_circle_top"]
    radius = abs(top[1] - center[1])
    assert radius == pytest.approx(PENALTY_ARC_RADIUS_M, abs=1e-3)


@pytest.mark.parametrize("side", ["left", "right"])
def test_penalty_arc_matches_intersection_points(
    kiki_points: dict[str, tuple[float, float, float]],
    side: str,
) -> None:
    geom = _penalty_arc_geometry(kiki_points, side)
    assert geom is not None
    assert geom["radius"] == pytest.approx(PENALTY_ARC_RADIUS_M, abs=1e-3)

    # Endpoints must land on the stored arc–penalty-line intersections (±1 mm).
    left_key = f"{side}_penalty_arc_left_intersection"
    right_key = f"{side}_penalty_arc_right_intersection"
    end1 = _arc_endpoint(geom, geom["theta1"])
    end2 = _arc_endpoint(geom, geom["theta2"])
    stored = {left_key: kiki_points[left_key][:2], right_key: kiki_points[right_key][:2]}

    def nearest(pt: tuple[float, float]) -> float:
        return min(math.hypot(pt[0] - sx, pt[1] - sy) for sx, sy in stored.values())

    assert nearest(end1) < 1e-3
    assert nearest(end2) < 1e-3

    # Arc mid-angle must bulge toward midfield (outside the penalty area), not into the goal.
    mid_ang = 0.5 * (geom["theta1"] + geom["theta2"])
    mid = _arc_endpoint(geom, mid_ang)
    spot_x = kiki_points[f"{side}_penalty_spot"][0]
    box_x = kiki_points[f"{side}_pen_box_top_inner"][0]
    if side == "left":
        # Midfield is +X from the left box; mid point X > box line X.
        assert mid[0] > box_x
        assert mid[0] > spot_x  # past the spot toward centre
    else:
        assert mid[0] < box_x
        assert mid[0] < spot_x


def test_penalty_arc_theta_matches_law1_formula(
    kiki_points: dict[str, tuple[float, float, float]],
) -> None:
    spot = kiki_points["left_penalty_spot"]
    box = kiki_points["left_pen_box_top_inner"]
    top = kiki_points["center_circle_top"]
    center = kiki_points["center_field"]
    radius = abs(top[1] - center[1])
    dx = abs(box[0] - spot[0])
    expected = math.acos(dx / radius)
    geom = _penalty_arc_geometry(kiki_points, "left")
    assert geom is not None
    assert geom["theta2"] == pytest.approx(expected, abs=1e-6)
    assert geom["theta1"] == pytest.approx(-expected, abs=1e-6)
