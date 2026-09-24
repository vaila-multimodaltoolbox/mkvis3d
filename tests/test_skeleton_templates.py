"""Structural tests for the detailed MHR-70/Goliath skeleton maps (0-based pN)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).parent.parent / "skeleton_templates"


@pytest.mark.parametrize(
    ("name", "expected_points"),
    [("sam3dinov3_mhr70", 70), ("sapiens2_goliath308", 308)],
)
def test_detailed_skeleton_connections_are_valid_and_unique(name, expected_points):
    template = json.loads((TEMPLATES / f"{name}.json").read_text())
    connections = [tuple(pair) for pair in template["connections"]]
    assert template["num_keypoints"] == expected_points
    assert len(connections) == len(set(connections))
    for pair in connections:
        assert len(pair) == 2
        assert all(0 <= int(point.removeprefix("p")) < expected_points for point in pair)


@pytest.mark.parametrize("name", ["sam3dinov3_mhr70", "sapiens2_goliath308"])
def test_detailed_models_include_neck_shoulders_elbow_planes_and_fingers(name):
    template = json.loads((TEMPLATES / f"{name}.json").read_text())
    edges = {frozenset(pair) for pair in template["connections"]}

    required = [
        ("p69", "p0"),  # neck to face, never ear to shoulder
        ("p69", "p67"),
        ("p69", "p68"),
        ("p67", "p5"),
        ("p6", "p68"),  # four-point shoulder girdle
        ("p7", "p63"),
        ("p7", "p65"),
        ("p63", "p65"),  # left elbow plane
        ("p8", "p64"),
        ("p8", "p66"),
        ("p64", "p66"),  # right elbow plane
        ("p62", "p45"),
        ("p45", "p44"),
        ("p41", "p24"),
        ("p24", "p23"),  # both hands/fingers
    ]
    assert all(frozenset(pair) in edges for pair in required)
    assert frozenset(("p3", "p5")) not in edges
    assert frozenset(("p4", "p6")) not in edges


@pytest.mark.parametrize(
    ("canonical", "legacy"),
    [
        ("sam3dinov3_mhr70", "skeleton_pose_sam3dinov3"),
        ("sapiens2_goliath308", "skeleton_pose_sapiens2"),
    ],
)
def test_legacy_template_aliases_match_canonical_connections(canonical, legacy):
    canonical_data = json.loads((TEMPLATES / f"{canonical}.json").read_text())
    legacy_data = json.loads((TEMPLATES / f"{legacy}.json").read_text())
    assert legacy_data["connections"] == canonical_data["connections"]


def test_skeleton_side_colors_match_vaila():
    from openbiomech.skeleton import (
        COLOR_CENTER_HEX,
        COLOR_CENTER_RGB,
        COLOR_LEFT_HEX,
        COLOR_LEFT_RGB,
        COLOR_RIGHT_HEX,
        COLOR_RIGHT_RGB,
    )

    # Must strictly follow vaila/sam3dinov3.py & vaila/sam3dinov3_visualize.py:
    # Left = Green (0, 255, 0), Right = Orange (255, 128, 0), Center = Blue (51, 153, 255)
    assert COLOR_LEFT_RGB == (0, 255, 0)
    assert COLOR_RIGHT_RGB == (255, 128, 0)
    assert COLOR_CENTER_RGB == (51, 153, 255)
    assert COLOR_LEFT_HEX.lower() == "#00ff00"
    assert COLOR_RIGHT_HEX.lower() == "#ff8000"
    assert COLOR_CENTER_HEX.lower() == "#3399ff"


@pytest.mark.parametrize(
    "template_name",
    [
        "sam3dinov3_mhr70",
        "sapiens2_goliath308",
        "yolo_coco17",
        "fifa_body15",
        "openpose_body25",
        "halpe26",
        "mediapipe_pose33",
        "mediapipe_hands42",
        "mediapipe_holistic75",
        "coco_wholebody133",
    ],
)
def test_human_body_templates_have_symmetric_side_connections(template_name):
    from openbiomech.skeleton import (
        COLOR_CENTER_RGB,
        COLOR_LEFT_RGB,
        COLOR_RIGHT_RGB,
        classify_template_connections,
    )

    template = json.loads((TEMPLATES / f"{template_name}.json").read_text())
    conns = classify_template_connections(template)

    left_conns = [c for c in conns if c["side"] == "left"]
    right_conns = [c for c in conns if c["side"] == "right"]
    center_conns = [c for c in conns if c["side"] == "center"]

    # All human body models must have identical number of left and right connections
    assert len(left_conns) == len(right_conns)
    assert len(left_conns) > 0
    assert len(left_conns) + len(right_conns) + len(center_conns) == len(conns)

    # Every left connection must carry Left Green color
    for c in left_conns:
        assert c["color_rgb"] == COLOR_LEFT_RGB
        assert c["color_hex"] == "#00ff00"

    # Every right connection must carry Right Orange color
    for c in right_conns:
        assert c["color_rgb"] == COLOR_RIGHT_RGB
        assert c["color_hex"] == "#ff8000"

    # Every center connection must carry Center Blue color
    for c in center_conns:
        assert c["color_rgb"] == COLOR_CENTER_RGB
        assert c["color_hex"] == "#3399ff"


def test_vicon_squat_and_mocap_lateralization():
    from openbiomech.skeleton import (
        COLOR_CENTER_RGB,
        COLOR_LEFT_RGB,
        COLOR_RIGHT_RGB,
        get_bone_side,
        get_marker_side,
        get_side_color_rgb,
    )

    # Portuguese D_ / E_ labels
    assert get_marker_side("D_joelho") == "right"
    assert get_marker_side("E_joelho") == "left"
    assert get_marker_side("barra_centro") == "center"

    assert get_bone_side("left", "left") == "left"
    assert get_bone_side("right", "right") == "right"
    assert get_bone_side("left", "right") == "center"
    assert get_bone_side("left", "center") == "center"

    assert get_side_color_rgb(get_bone_side("left", "left")) == COLOR_LEFT_RGB
    assert get_side_color_rgb(get_bone_side("right", "right")) == COLOR_RIGHT_RGB
    assert get_side_color_rgb(get_bone_side("left", "right")) == COLOR_CENTER_RGB

    # Standard mocap acronyms
    assert get_marker_side("LASI") == "left"
    assert get_marker_side("RASI") == "right"
    assert get_marker_side("LANK") == "left"
    assert get_marker_side("RANK") == "right"
    assert get_marker_side("CLAV") == "center"


def test_soccerfield_kiki49_connections_are_valid():
    template = json.loads((TEMPLATES / "soccerfield_kiki49.json").read_text())
    assert template["num_keypoints"] == 49
    assert len(template["keypoints"]) == 49
    connections = [tuple(pair) for pair in template["connections"]]
    assert len(connections) == len({frozenset(p) for p in connections})
    for pair in connections:
        assert len(pair) == 2
        assert all(0 <= int(point.removeprefix("p")) < 49 for point in pair)

    edges = {frozenset(pair) for pair in connections}
    # Goal posts, crossbar, net depth, corner flag masts
    required = [
        ("p32", "p34"),
        ("p33", "p35"),
        ("p34", "p35"),
        ("p32", "p36"),
        ("p33", "p37"),
        ("p36", "p37"),
        ("p40", "p42"),
        ("p41", "p43"),
        ("p42", "p43"),
        ("p40", "p44"),
        ("p41", "p45"),
        ("p44", "p45"),
        ("p0", "p38"),
        ("p5", "p39"),
        ("p24", "p46"),
        ("p29", "p47"),
    ]
    assert all(frozenset(pair) in edges for pair in required)
    # No diamond approximation of the center circle (drawn procedurally)
    for diamond in (("p14", "p30"), ("p30", "p15"), ("p15", "p31"), ("p31", "p14")):
        assert frozenset(diamond) not in edges


def test_soccerfield_kiki49_matches_custom_c3d_labels():
    from openbiomech.c3d_io import read_c3d_native

    c3d_path = Path(__file__).parent.parent / "data" / "soccerfield_kiki_custom.c3d"
    if not c3d_path.is_file():
        pytest.skip(f"missing fixture {c3d_path}")
    template = json.loads((TEMPLATES / "soccerfield_kiki49.json").read_text())
    trial = read_c3d_native(c3d_path)
    assert list(trial.labels) == template["keypoints"]
