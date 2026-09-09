"""Tests for signal filtering, smoothing, and gap filling routines."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from openbiomech.biomech_math.filtering import (
    butterworth_filter,
    gap_fill_1d,
    hampel_filter,
    median_filter,
    moving_average,
    process_marker_trial,
)
from openbiomech.c3d_io import read_c3d_native

FIXTURE_C3D = Path(__file__).parent.parent / "data" / "rec3d_20260826_121305_m.c3d"


def test_gap_fill_linear():
    # Linear ramp with a gap
    s = np.array([0.0, 1.0, np.nan, np.nan, 4.0, 5.0])
    filled = gap_fill_1d(s, method="linear")
    expected = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    assert np.allclose(filled, expected)


def test_gap_fill_max_gap_limit():
    # Gap of 3 frames; max_gap=2 should NOT fill it
    s = np.array([0.0, np.nan, np.nan, np.nan, 4.0])
    filled = gap_fill_1d(s, method="linear", max_gap=2)
    assert np.isnan(filled[1]) and np.isnan(filled[2]) and np.isnan(filled[3])

    # max_gap=3 SHOULD fill it
    filled3 = gap_fill_1d(s, method="linear", max_gap=3)
    assert not np.any(np.isnan(filled3))
    assert np.allclose(filled3, np.array([0.0, 1.0, 2.0, 3.0, 4.0]))


def test_gap_fill_cubic():
    t = np.linspace(0, np.pi, 25)
    clean_sine = np.sin(t)
    corrupted = clean_sine.copy()
    corrupted[10:13] = np.nan

    filled = gap_fill_1d(corrupted, method="cubic")
    assert not np.any(np.isnan(filled))
    # Cubic spline on smooth sine curve should be very close to original
    assert np.allclose(filled, clean_sine, atol=0.05)


def test_hampel_filter_removes_spike():
    data = np.ones(50) * 10.0
    data[25] = 100.0  # Large tracking spike
    cleaned = hampel_filter(data, window_size=7, n_sigmas=3.0)
    assert cleaned[25] < 15.0
    assert np.isclose(cleaned[25], 10.0)


def test_median_filter_and_moving_average():
    data = np.array([1.0, 1.0, 10.0, 1.0, 1.0, 1.0])
    med = median_filter(data, kernel_size=3)
    assert med[2] == 1.0  # Impulse spike rejected

    ma = moving_average(np.ones(20) * 5.0, window_size=5)
    assert np.allclose(ma, 5.0)


def test_butterworth_filter_attenuates_high_frequency():
    fs = 100.0
    t = np.arange(0, 2.0, 1.0 / fs)
    # Low frequency 2 Hz + High frequency 25 Hz noise
    sig_low = np.sin(2 * np.pi * 2.0 * t)
    sig_high = 0.5 * np.sin(2 * np.pi * 25.0 * t)
    composite = sig_low + sig_high

    filtered = butterworth_filter(composite, sample_rate=fs, cutoff=6.0, order=4)
    # Filter should preserve 2Hz signal while attenuating 25Hz noise
    error = filtered[20:-20] - sig_low[20:-20]
    assert np.std(error) < 0.1


def test_process_marker_trial_on_fixture():
    trial = read_c3d_native(FIXTURE_C3D)
    processed = process_marker_trial(
        trial,
        interp_method="linear",
        max_gap=15,
        smooth_method="butterworth",
        cutoff_hz=6.0,
        order=4,
    )
    assert processed.n_frames == trial.n_frames
    assert processed.n_markers == trial.n_markers
    assert processed.labels == trial.labels
    # Confirm processed data is finite where original was finite
    finite_mask = np.isfinite(trial.xyz)
    assert np.all(np.isfinite(processed.xyz[finite_mask]))
