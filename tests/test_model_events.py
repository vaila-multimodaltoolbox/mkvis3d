"""Tests for `openbiomech/model/events.py` (Zeni et al. 2008 gait events)."""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.model.events import detect_gait_events
from openbiomech.model.landmark import Landmark


def _sine_landmark(name: str, n_frames: int, *, amplitude: float, period_frames: float, axis: int):
    t = np.arange(n_frames, dtype=np.float64)
    signal = amplitude * np.sin(2.0 * np.pi * t / period_frames)
    positions = np.zeros((n_frames, 3))
    positions[:, axis] = signal
    return Landmark(name=name, positions=positions)


def test_detects_known_maxima_and_minima_of_a_sine_signal():
    n_frames, period = 200, 20.0
    heel = _sine_landmark("heel", n_frames, amplitude=1.0, period_frames=period, axis=1)
    sacrum = Landmark(name="sacrum", positions=np.zeros((n_frames, 3)))

    events = detect_gait_events(heel, sacrum, progression_axis=1)

    # sin() peaks at period/4 + k*period, troughs at 3*period/4 + k*period
    expected_peaks = np.round(period / 4 + period * np.arange(10)).astype(int)
    expected_troughs = np.round(3 * period / 4 + period * np.arange(10)).astype(int)
    expected_peaks = expected_peaks[expected_peaks < n_frames - 1]
    expected_troughs = expected_troughs[expected_troughs < n_frames - 1]

    assert np.array_equal(events["heel_strike"], expected_peaks)
    assert np.array_equal(events["toe_off"], expected_troughs)


def test_uses_relative_signal_not_absolute_position():
    # heel is static in the world, but the reference marker moves forward
    # linearly with a superimposed oscillation -> relative signal still
    # oscillates and is detected, even though heel's own trajectory is flat.
    n_frames, period = 60, 10.0
    t = np.arange(n_frames, dtype=np.float64)
    heel = Landmark(name="heel", positions=np.zeros((n_frames, 3)))
    ref_positions = np.zeros((n_frames, 3))
    ref_positions[:, 0] = -np.sin(2.0 * np.pi * t / period)  # relative = +sin
    reference = Landmark(name="sacrum", positions=ref_positions)

    events = detect_gait_events(heel, reference, progression_axis=0)
    assert events["heel_strike"].size > 0
    assert events["toe_off"].size > 0


def test_occlusion_gaps_never_produce_a_false_event():
    n_frames = 30
    positions = np.zeros((n_frames, 3))
    positions[10:15, 1] = np.nan
    heel = Landmark(name="heel", positions=positions)
    sacrum = Landmark(name="sacrum", positions=np.zeros((n_frames, 3)))

    events = detect_gait_events(heel, sacrum, progression_axis=1)
    assert events["heel_strike"].size == 0
    assert events["toe_off"].size == 0


def test_mismatched_shapes_raise_value_error():
    heel = Landmark(name="heel", positions=np.zeros((10, 3)))
    sacrum = Landmark(name="sacrum", positions=np.zeros((5, 3)))
    with pytest.raises(ValueError, match="shapes must match"):
        detect_gait_events(heel, sacrum, progression_axis=0)


def test_invalid_axis_raises_value_error():
    heel = Landmark(name="heel", positions=np.zeros((10, 3)))
    sacrum = Landmark(name="sacrum", positions=np.zeros((10, 3)))
    with pytest.raises(ValueError, match="progression_axis"):
        detect_gait_events(heel, sacrum, progression_axis=3)


def test_short_trial_returns_no_events_without_crashing():
    heel = Landmark(name="heel", positions=np.zeros((2, 3)))
    sacrum = Landmark(name="sacrum", positions=np.zeros((2, 3)))
    events = detect_gait_events(heel, sacrum, progression_axis=0)
    assert events["heel_strike"].size == 0
    assert events["toe_off"].size == 0
