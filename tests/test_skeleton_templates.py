"""Structural tests for the detailed MHR-70/Goliath skeleton maps."""

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
        assert all(1 <= int(point.removeprefix("p")) <= expected_points for point in pair)


@pytest.mark.parametrize("name", ["sam3dinov3_mhr70", "sapiens2_goliath308"])
def test_detailed_models_include_neck_shoulders_elbow_planes_and_fingers(name):
    template = json.loads((TEMPLATES / f"{name}.json").read_text())
    edges = {frozenset(pair) for pair in template["connections"]}

    required = [
        ("p70", "p1"),  # neck to face, never ear to shoulder
        ("p70", "p68"),
        ("p70", "p69"),
        ("p68", "p6"),
        ("p7", "p69"),  # four-point shoulder girdle
        ("p8", "p64"),
        ("p8", "p66"),
        ("p64", "p66"),  # left elbow plane
        ("p9", "p65"),
        ("p9", "p67"),
        ("p65", "p67"),  # right elbow plane
        ("p63", "p46"),
        ("p46", "p45"),
        ("p42", "p25"),
        ("p25", "p24"),  # both hands/fingers
    ]
    assert all(frozenset(pair) in edges for pair in required)
    assert frozenset(("p4", "p6")) not in edges
    assert frozenset(("p5", "p7")) not in edges


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
