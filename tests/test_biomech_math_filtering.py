"""Synthetic ground-truth test for the Butterworth zero-phase filter."""

from __future__ import annotations

import numpy as np

from openbiomech.biomech_math import butterworth_filter


def test_butterworth_attenuates_high_frequency_noise_without_phase_lag():
    sample_rate = 100.0
    duration_s = 5.0
    t = np.arange(0, duration_s, 1.0 / sample_rate)

    signal_hz = 1.0  # well below the 6 Hz default cutoff
    noise_hz = 30.0  # well above it
    clean = np.sin(2 * np.pi * signal_hz * t)
    noisy = clean + 0.5 * np.sin(2 * np.pi * noise_hz * t)

    filtered = butterworth_filter(noisy[:, None], sample_rate, cutoff=6.0)[:, 0]

    # High-frequency content should be strongly attenuated.
    residual_after_removing_clean = filtered - clean
    assert np.std(residual_after_removing_clean) < 0.05

    # Zero-phase: no lag between filtered and the known-clean signal, i.e.
    # cross-correlation peaks at lag 0 (a lagged filter would peak elsewhere).
    lags = np.arange(-5, 6)
    corr_at_lag = [
        np.corrcoef(filtered[5 : -5 or None], np.roll(clean, lag)[5 : -5 or None])[0, 1]
        for lag in lags
    ]
    assert lags[int(np.argmax(corr_at_lag))] == 0


def test_butterworth_rejects_invalid_cutoff():
    import pytest

    data = np.zeros((50, 1))
    with pytest.raises(ValueError):
        butterworth_filter(data, sample_rate=100.0, cutoff=60.0)  # >= Nyquist
