"""Tests for marker-defined quaternion and multi-sequence Euler analysis."""

from __future__ import annotations

import numpy as np
from numpy.testing import assert_allclose

from openbiomech.kinematic_analysis import TAIT_BRYAN_SEQUENCES, marker_frame_orientations
from openbiomech.marker_trial import MarkerTrial


def test_marker_frame_reports_identity_in_all_sequences_and_wxyz_quaternion():
    xyz = np.array(
        [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[1.0, 2.0, 3.0], [2.0, 2.0, 3.0], [1.0, 3.0, 3.0]],
        ],
        dtype=np.float64,
    )
    trial = MarkerTrial(("origin", "x", "plane"), 100.0, xyz, np.zeros((2, 3)))

    result = marker_frame_orientations(trial, "origin", "x", "plane")

    assert result["quaternion_convention"] == "scalar-first wxyz"
    assert_allclose(result["rotation_matrices"], np.tile(np.eye(3), (2, 1, 1)))
    assert_allclose(result["quaternions"], [[1.0, 0.0, 0.0, 0.0]] * 2)
    assert set(result["euler"]) == set(TAIT_BRYAN_SEQUENCES)
    for sequence in TAIT_BRYAN_SEQUENCES:
        assert_allclose(result["euler"][sequence], 0.0, atol=1e-12)
        assert_allclose(result["gimbal_lock_margin_degrees"][sequence], 90.0)


def test_marker_frame_marks_collinear_or_missing_frames_invalid():
    xyz = np.array(
        [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            [[np.nan] * 3, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        ],
        dtype=np.float64,
    )
    trial = MarkerTrial(("origin", "x", "plane"), 100.0, xyz, np.zeros((2, 3)))
    result = marker_frame_orientations(trial, "origin", "x", "plane")
    assert not result["valid"].any()
    assert np.isnan(result["quaternions"]).all()
