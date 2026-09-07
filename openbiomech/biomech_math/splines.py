"""Generalised cross-validatory smoothing splines and smooth differentiation.

README.md §3.4 calls for GCVSPL — Woltring's generalised cross-validatory
spline — to produce continuous first and second derivatives (velocity,
acceleration, angular velocity and its rate) without the high-frequency noise
amplification that finite differencing of digitised coordinates causes.

SciPy already implements exactly that criterion in
`scipy.interpolate.make_smoothing_spline`, which chooses the smoothing
parameter by generalised cross-validation and returns a `BSpline` whose
analytic derivatives are available directly, so this module supplies the
biomechanics-facing API (sampling rate instead of a time vector, per-marker
batching, gap handling) rather than re-deriving the numerics.

Differences from Woltring's original Fortran worth knowing: that routine
offers cubic *and* quintic order and reports the GCV score itself, whereas
`make_smoothing_spline` is cubic-only. Cubic is enough for the C2 continuity
the first two derivatives need; a quintic option would have to come from
`scipy.interpolate.splrep`'s `k=5` with a manually selected `s`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import BSpline, make_smoothing_spline

# make_smoothing_spline fits a cubic spline, so it needs at least this many
# distinct samples before the fit is determined.
MIN_SAMPLES = 5


@dataclass
class SmoothingSpline:
    """A fitted GCV smoothing spline over one scalar time series."""

    spline: BSpline
    lam: float | None
    n_samples: int

    def __call__(self, t: np.ndarray) -> np.ndarray:
        """Evaluate the smoothed signal at times `t`."""
        return np.asarray(self.spline(np.asarray(t, dtype=np.float64)), dtype=np.float64)

    def derivative(self, t: np.ndarray, order: int = 1) -> np.ndarray:
        """Evaluate the `order`-th analytic derivative at times `t`.

        A cubic spline's third and higher derivatives are piecewise constant
        or zero, so `order > 2` is not meaningful here and is rejected.
        """
        if order < 0:
            raise ValueError(f"derivative order must be >= 0, got {order}")
        if order > 2:
            raise ValueError(
                f"a cubic smoothing spline supports derivatives up to order 2, got {order}"
            )
        if order == 0:
            return self(t)
        return np.asarray(
            self.spline.derivative(order)(np.asarray(t, dtype=np.float64)), dtype=np.float64
        )


def fit_smoothing_spline(
    t: np.ndarray, y: np.ndarray, *, lam: float | None = None
) -> SmoothingSpline:
    """Fit a cubic smoothing spline to one scalar series.

    Args:
        t: `(N,)` strictly increasing sample times.
        y: `(N,)` observations. Non-finite samples (occluded markers) are
            dropped before fitting; the spline still evaluates across the gap.
        lam: smoothing parameter. `None` (the default) selects it by
            generalised cross-validation, which is the GCVSPL behaviour
            README.md §3.4 asks for. A larger value smooths harder; 0 would
            interpolate.

    Raises:
        ValueError: if fewer than `MIN_SAMPLES` finite samples remain, or if
            `t` is not strictly increasing.
    """
    times = np.asarray(t, dtype=np.float64).ravel()
    values = np.asarray(y, dtype=np.float64).ravel()
    if times.shape != values.shape:
        raise ValueError(f"t and y must have the same length, got {times.shape} and {values.shape}")

    finite = np.isfinite(times) & np.isfinite(values)
    times, values = times[finite], values[finite]
    if times.size < MIN_SAMPLES:
        raise ValueError(
            f"need at least {MIN_SAMPLES} finite samples to fit a cubic smoothing spline, "
            f"got {times.size}"
        )
    if np.any(np.diff(times) <= 0):
        raise ValueError("t must be strictly increasing after dropping non-finite samples")

    spline = make_smoothing_spline(times, values, lam=lam)
    return SmoothingSpline(spline=spline, lam=lam, n_samples=int(times.size))


def smooth_derivatives(
    data: np.ndarray,
    sample_rate: float,
    *,
    lam: float | None = None,
    max_order: int = 2,
) -> tuple[np.ndarray, ...]:
    """Smooth a uniformly sampled signal and differentiate it analytically.

    The intended use is turning filtered marker coordinates into velocity and
    acceleration without differencing noise, per README.md §3.4.

    Args:
        data: `(n_samples,)` or `(n_samples, n_series)` — one column per
            coordinate or channel. Columns are fitted independently, so an
            occluded marker does not contaminate its neighbours.
        sample_rate: sampling frequency in Hz; sets the time base, so
            derivatives come out in units-per-second and units-per-second².
        lam: passed through to `fit_smoothing_spline`; `None` means GCV.
        max_order: highest derivative to return (0, 1 or 2).

    Returns:
        `max_order + 1` arrays shaped like `data`: the smoothed signal, then
        each successive derivative. Columns whose finite samples fall below
        `MIN_SAMPLES` come back as all-NaN rather than raising, so one dead
        marker does not fail the whole trial.
    """
    if sample_rate <= 0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate}")
    if not 0 <= max_order <= 2:
        raise ValueError(f"max_order must be 0, 1 or 2, got {max_order}")

    arr = np.asarray(data, dtype=np.float64)
    one_dimensional = arr.ndim == 1
    if one_dimensional:
        arr = arr[:, None]
    if arr.ndim != 2:
        raise ValueError(f"expected (n_samples,) or (n_samples, n_series), got {arr.shape}")

    n_samples, n_series = arr.shape
    times = np.arange(n_samples, dtype=np.float64) / float(sample_rate)
    outputs = [np.full_like(arr, np.nan) for _ in range(max_order + 1)]

    for column in range(n_series):
        try:
            fitted = fit_smoothing_spline(times, arr[:, column], lam=lam)
        except ValueError:
            continue  # too few finite samples in this column; leave it NaN
        for order in range(max_order + 1):
            outputs[order][:, column] = fitted.derivative(times, order=order)

    if one_dimensional:
        return tuple(out[:, 0] for out in outputs)
    return tuple(outputs)
