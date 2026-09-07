"""Phase-2 verifier: GCV smoothing splines and smooth differentiation.

The ground truth is a sine whose first and second derivatives are known in
closed form, sampled with additive noise. The point of README.md §3.4 is that
finite differencing amplifies that noise while a smoothing spline does not, so
the decisive assertions compare both against the analytic derivative.
"""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.biomech_math import fit_smoothing_spline, smooth_derivatives
from openbiomech.biomech_math.splines import MIN_SAMPLES

RATE_HZ = 100.0
FREQ_HZ = 1.0
DURATION_S = 4.0


def _noisy_sine(noise_sd: float = 0.01, seed: int = 0):
    """Return (t, clean, noisy, velocity, acceleration) for a 1 Hz sine."""
    t = np.arange(0.0, DURATION_S, 1.0 / RATE_HZ)
    omega = 2.0 * np.pi * FREQ_HZ
    clean = np.sin(omega * t)
    velocity = omega * np.cos(omega * t)
    acceleration = -(omega**2) * np.sin(omega * t)
    rng = np.random.default_rng(seed)
    noisy = clean + rng.normal(scale=noise_sd, size=t.size)
    return t, clean, noisy, velocity, acceleration


# --------------------------------------------------------------------------
# Fitting one series
# --------------------------------------------------------------------------


def test_smoothing_spline_recovers_the_underlying_signal():
    t, clean, noisy, _, _ = _noisy_sine()

    fitted = fit_smoothing_spline(t, noisy)
    smoothed = fitted(t)

    assert fitted.n_samples == t.size
    # The fit must be closer to the truth than the raw data it was given.
    assert np.std(smoothed - clean) < np.std(noisy - clean)
    assert np.max(np.abs(smoothed - clean)) < 0.02


def test_smoothing_spline_derivatives_match_the_analytic_ones():
    t, _, noisy, velocity, acceleration = _noisy_sine()

    fitted = fit_smoothing_spline(t, noisy)

    # Trim the edges: a spline is least constrained at its boundary knots.
    interior = slice(20, -20)
    assert np.max(np.abs(fitted.derivative(t, 1)[interior] - velocity[interior])) < 0.3
    assert np.max(np.abs(fitted.derivative(t, 2)[interior] - acceleration[interior])) < 8.0


def test_spline_derivative_beats_finite_differencing_on_noisy_data():
    """The reason README.md §3.4 asks for GCVSPL instead of differencing."""
    t, _, noisy, velocity, acceleration = _noisy_sine()
    interior = slice(20, -20)

    fitted = fit_smoothing_spline(t, noisy)
    spline_velocity = fitted.derivative(t, 1)
    spline_acceleration = fitted.derivative(t, 2)

    fd_velocity = np.gradient(noisy, t)
    fd_acceleration = np.gradient(fd_velocity, t)

    spline_v_err = np.std(spline_velocity[interior] - velocity[interior])
    fd_v_err = np.std(fd_velocity[interior] - velocity[interior])
    spline_a_err = np.std(spline_acceleration[interior] - acceleration[interior])
    fd_a_err = np.std(fd_acceleration[interior] - acceleration[interior])

    assert spline_v_err < fd_v_err
    # Second differences amplify noise far more, so the gap widens sharply.
    assert spline_a_err < 0.1 * fd_a_err


def test_larger_lambda_smooths_harder():
    t, _, noisy, _, _ = _noisy_sine()

    light = fit_smoothing_spline(t, noisy, lam=1e-9)(t)
    heavy = fit_smoothing_spline(t, noisy, lam=1e-2)(t)

    assert np.std(np.diff(heavy, 2)) < np.std(np.diff(light, 2))
    assert fit_smoothing_spline(t, noisy, lam=1e-2).lam == 1e-2


def test_non_finite_samples_are_dropped_before_fitting():
    t, clean, noisy, _, _ = _noisy_sine()
    gapped = noisy.copy()
    gapped[100:110] = np.nan  # a 0.1 s occlusion

    fitted = fit_smoothing_spline(t, gapped)

    assert fitted.n_samples == t.size - 10
    # The spline still evaluates across the gap, close to the true signal.
    # Accuracy there degrades with gap length -- a gap approaching a full
    # period of the underlying motion cannot be recovered by smoothness alone.
    assert np.max(np.abs(fitted(t[100:110]) - clean[100:110])) < 0.05


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------


def test_rejects_too_few_samples():
    t = np.arange(MIN_SAMPLES - 1, dtype=float)
    with pytest.raises(ValueError, match="at least"):
        fit_smoothing_spline(t, np.zeros_like(t))


def test_rejects_non_increasing_times():
    t = np.array([0.0, 0.2, 0.1, 0.3, 0.4, 0.5])
    with pytest.raises(ValueError, match="strictly increasing"):
        fit_smoothing_spline(t, np.zeros_like(t))


def test_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        fit_smoothing_spline(np.arange(6.0), np.arange(5.0))


def test_rejects_derivative_order_above_two():
    t, _, noisy, _, _ = _noisy_sine()
    fitted = fit_smoothing_spline(t, noisy)
    with pytest.raises(ValueError, match="order 2"):
        fitted.derivative(t, order=3)


# --------------------------------------------------------------------------
# Batched differentiation over marker columns
# --------------------------------------------------------------------------


def test_smooth_derivatives_returns_signal_velocity_acceleration():
    _, _, noisy, velocity, acceleration = _noisy_sine()

    smoothed, v, a = smooth_derivatives(noisy, RATE_HZ)

    interior = slice(20, -20)
    assert smoothed.shape == v.shape == a.shape == noisy.shape
    assert np.max(np.abs(v[interior] - velocity[interior])) < 0.3
    assert np.max(np.abs(a[interior] - acceleration[interior])) < 8.0


def test_smooth_derivatives_handles_multiple_columns_independently():
    t, clean, noisy, velocity, _ = _noisy_sine()
    # Column 1 is the same signal scaled; column 2 is entirely missing.
    data = np.column_stack([noisy, 2.0 * noisy, np.full_like(noisy, np.nan)])

    smoothed, v = smooth_derivatives(data, RATE_HZ, max_order=1)

    interior = slice(20, -20)
    assert smoothed.shape == data.shape
    assert np.max(np.abs(smoothed[interior, 0] - clean[interior])) < 0.02
    assert np.max(np.abs(v[interior, 1] - 2.0 * velocity[interior])) < 0.6
    # A dead marker yields NaN instead of failing the whole trial.
    assert np.all(np.isnan(smoothed[:, 2]))
    assert np.all(np.isnan(v[:, 2]))


def test_smooth_derivatives_respects_max_order():
    _, _, noisy, _, _ = _noisy_sine()
    assert len(smooth_derivatives(noisy, RATE_HZ, max_order=0)) == 1
    assert len(smooth_derivatives(noisy, RATE_HZ, max_order=2)) == 3


def test_smooth_derivatives_uses_sample_rate_as_the_time_base():
    """Derivatives come out per second, so the same samples read at half the
    rate give half the velocity.

    A linear ramp makes this exact: its slope is recovered whatever smoothing
    parameter GCV settles on, so the assertion tests the time base alone. (A
    curved signal would not scale exactly, because changing the time base also
    changes which lambda GCV selects.)
    """
    ramp = 3.0 * np.arange(200, dtype=np.float64) / RATE_HZ  # 3 units/second

    _, fast = smooth_derivatives(ramp, RATE_HZ, max_order=1)
    _, slow = smooth_derivatives(ramp, RATE_HZ / 2.0, max_order=1)

    interior = slice(20, -20)
    assert np.allclose(fast[interior], 3.0, atol=1e-6)
    assert np.allclose(slow[interior], 1.5, atol=1e-6)


def test_smooth_derivatives_rejects_invalid_arguments():
    _, _, noisy, _, _ = _noisy_sine()
    with pytest.raises(ValueError, match="sample_rate"):
        smooth_derivatives(noisy, 0.0)
    with pytest.raises(ValueError, match="max_order"):
        smooth_derivatives(noisy, RATE_HZ, max_order=3)
