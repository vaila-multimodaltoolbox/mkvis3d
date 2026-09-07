"""Synthetic ground-truth tests for landmark trajectories."""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.marker_trial import MarkerTrial
from openbiomech.model import Landmark, landmark_from_trial, virtual_midpoint


def _trial() -> MarkerTrial:
    xyz = np.zeros((4, 2, 3))
    xyz[:, 0, :] = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]]
    xyz[:, 1, :] = [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0], [2.0, 2.0, 0.0], [3.0, 2.0, 0.0]]
    xyz[2, 1, :] = np.nan  # occluded frame on the second marker
    return MarkerTrial(
        labels=("left", "right"),
        rate_hz=100.0,
        xyz=xyz,
        residuals=np.zeros((4, 2)),
    )


def test_landmark_from_trial_copies_the_named_marker():
    trial = _trial()

    lm = landmark_from_trial(trial, "left")

    assert lm.name == "left"
    assert not lm.virtual
    assert np.array_equal(lm.positions, trial.marker("left"))
    assert lm.n_frames == 4


def test_landmark_from_trial_copy_is_independent_of_the_source_trial():
    trial = _trial()
    lm = landmark_from_trial(trial, "left")

    lm.positions[0, 0] = 999.0

    assert trial.marker("left")[0, 0] == 0.0


def test_landmark_from_trial_accepts_a_custom_name():
    trial = _trial()

    lm = landmark_from_trial(trial, "left", name="asis_l")

    assert lm.name == "asis_l"


def test_virtual_midpoint_averages_per_frame():
    trial = _trial()
    left = landmark_from_trial(trial, "left")
    right = landmark_from_trial(trial, "right")

    mid = virtual_midpoint(left, right, "mid")

    assert mid.virtual
    assert mid.name == "mid"
    expected = (left.positions + right.positions) / 2.0
    np.testing.assert_allclose(mid.positions, expected)
    # frame 0: left (0,0,0), right (0,2,0) -> midpoint (0,1,0)
    np.testing.assert_allclose(mid.positions[0], [0.0, 1.0, 0.0])


def test_virtual_midpoint_propagates_occlusion():
    trial = _trial()
    left = landmark_from_trial(trial, "left")
    right = landmark_from_trial(trial, "right")  # NaN at frame 2

    mid = virtual_midpoint(left, right, "mid")

    assert np.all(np.isnan(mid.positions[2]))
    assert not np.any(np.isnan(mid.positions[[0, 1, 3]]))


def test_virtual_midpoint_rejects_mismatched_shapes():
    a = Landmark(name="a", positions=np.zeros((4, 3)))
    b = Landmark(name="b", positions=np.zeros((5, 3)))

    with pytest.raises(ValueError, match="shapes must match"):
        virtual_midpoint(a, b, "mid")
