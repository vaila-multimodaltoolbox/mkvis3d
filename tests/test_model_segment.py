"""Synthetic ground-truth tests for segment geometry (length, longitudinal axis)."""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.model import Landmark, Segment


def test_segment_length_matches_known_distance():
    # A 3-4-5 right triangle offset in x/y/z.
    proximal = Landmark(name="p", positions=np.array([[0.0, 0.0, 0.0]]))
    distal = Landmark(name="d", positions=np.array([[3.0, 4.0, 0.0]]))

    seg = Segment(name="s", proximal=proximal, distal=distal)

    np.testing.assert_allclose(seg.length(), [5.0])


def test_segment_length_is_nan_when_a_landmark_is_occluded():
    proximal = Landmark(name="p", positions=np.array([[0.0, 0.0, 0.0], [np.nan] * 3]))
    distal = Landmark(name="d", positions=np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]]))

    seg = Segment(name="s", proximal=proximal, distal=distal)

    lengths = seg.length()
    assert lengths[0] == pytest.approx(1.0)
    assert np.isnan(lengths[1])


def test_longitudinal_axis_points_distal_to_proximal():
    # distal at the origin, proximal 2m straight up -> axis is +Z, unit length,
    # regardless of segment length.
    proximal = Landmark(name="p", positions=np.array([[0.0, 0.0, 2.0]]))
    distal = Landmark(name="d", positions=np.array([[0.0, 0.0, 0.0]]))

    seg = Segment(name="s", proximal=proximal, distal=distal)
    axis = seg.longitudinal_axis()

    np.testing.assert_allclose(axis, [[0.0, 0.0, 1.0]])
    np.testing.assert_allclose(np.linalg.norm(axis, axis=1), [1.0])


def test_longitudinal_axis_is_nan_for_zero_length_segment():
    same = np.array([[1.0, 2.0, 3.0]])
    proximal = Landmark(name="p", positions=same.copy())
    distal = Landmark(name="d", positions=same.copy())

    seg = Segment(name="s", proximal=proximal, distal=distal)

    assert np.all(np.isnan(seg.longitudinal_axis()))


def test_longitudinal_axis_is_nan_when_occluded():
    proximal = Landmark(name="p", positions=np.array([[0.0, 0.0, 1.0], [np.nan] * 3]))
    distal = Landmark(name="d", positions=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]))

    seg = Segment(name="s", proximal=proximal, distal=distal)
    axis = seg.longitudinal_axis()

    np.testing.assert_allclose(axis[0], [0.0, 0.0, 1.0])
    assert np.all(np.isnan(axis[1]))


def test_segment_rejects_mismatched_landmark_shapes():
    proximal = Landmark(name="p", positions=np.zeros((4, 3)))
    distal = Landmark(name="d", positions=np.zeros((5, 3)))

    with pytest.raises(ValueError, match="proximal landmark"):
        Segment(name="s", proximal=proximal, distal=distal)


def test_segment_n_frames():
    proximal = Landmark(name="p", positions=np.zeros((7, 3)))
    distal = Landmark(name="d", positions=np.zeros((7, 3)))

    seg = Segment(name="s", proximal=proximal, distal=distal)

    assert seg.n_frames == 7
