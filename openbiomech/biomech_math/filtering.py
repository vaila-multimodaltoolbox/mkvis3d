"""Trajectory smoothing, filtering, and gap-filling for biomechanics.

Implements standard biomechanics filtering routines matching
`/home/preto/data/vaila/vaila/interp_smooth_split.py`:
- 4th-order zero-phase (dual-pass) Butterworth low-pass filter (default 6.0 Hz).
- Linear, Cubic, and Nearest-neighbor gap-filling (interpolation) with gap-size limits.
- Median filter and Moving Average smoothing.
- Hampel outlier / spike filter (MAD-based).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, medfilt

from openbiomech.marker_trial import MarkerTrial


def gap_fill_1d(
    series: np.ndarray,
    method: str = "linear",
    max_gap: int | None = None,
) -> np.ndarray:
    """Fill NaN gaps in a 1D sequence using interpolation.

    Parameters:
        series: 1D array of floats with NaNs representing missing frames.
        method: 'linear', 'cubic', or 'nearest'.
        max_gap: Maximum consecutive NaN frames to fill. If None, fills all gaps.
            If gap length > max_gap, the gap remains NaN.
    """
    arr = np.asarray(series, dtype=np.float64).copy()
    n = len(arr)
    if n == 0:
        return arr

    nan_mask = np.isnan(arr)
    if not np.any(nan_mask):
        return arr
    if np.all(nan_mask):
        return arr

    # Find contiguous NaN blocks
    in_gap = False
    start_idx = 0
    gaps: list[tuple[int, int]] = []
    for i, is_nan in enumerate(nan_mask):
        if is_nan and not in_gap:
            in_gap = True
            start_idx = i
        elif not is_nan and in_gap:
            in_gap = False
            gaps.append((start_idx, i - 1))
    if in_gap:
        gaps.append((start_idx, n - 1))

    valid_indices = np.where(~nan_mask)[0]
    valid_values = arr[valid_indices]

    for g_start, g_end in gaps:
        gap_len = g_end - g_start + 1
        if max_gap is not None and gap_len > max_gap:
            continue

        # Check edge cases (gap at trial boundary)
        if g_start == 0:
            # Beginning of trial: clamp to first valid sample
            arr[g_start : g_end + 1] = valid_values[0]
            continue
        if g_end == n - 1:
            # End of trial: clamp to last valid sample
            arr[g_start : g_end + 1] = valid_values[-1]
            continue

        # Internal gap bounded by valid samples at g_start - 1 and g_end + 1
        i0 = g_start - 1
        i1 = g_end + 1
        y0 = arr[i0]
        y1 = arr[i1]
        x_gap = np.arange(g_start, g_end + 1, dtype=np.float64)

        if method == "nearest":
            mid = (i0 + i1) / 2.0
            arr[g_start : g_end + 1] = np.where(x_gap < mid, y0, y1)

        elif method == "cubic" and len(valid_indices) >= 4:
            # Cubic Hermite / Catmull-Rom interpolation with finite difference slopes
            # Find sample before i0 and sample after i1 if available
            prev_idx = i0 - 1 if i0 > 0 and not np.isnan(arr[i0 - 1]) else i0
            next_idx = i1 + 1 if i1 < n - 1 and not np.isnan(arr[i1 + 1]) else i1

            m0 = (arr[i1] - arr[prev_idx]) / max(1, i1 - prev_idx)
            m1 = (arr[next_idx] - arr[i0]) / max(1, next_idx - i0)

            dx = float(i1 - i0)
            t = (x_gap - i0) / dx
            t2 = t * t
            t3 = t2 * t

            h00 = 2.0 * t3 - 3.0 * t2 + 1.0
            h10 = t3 - 2.0 * t2 + t
            h01 = -2.0 * t3 + 3.0 * t2
            h11 = t3 - t2

            arr[g_start : g_end + 1] = h00 * y0 + h10 * dx * m0 + h01 * y1 + h11 * dx * m1
        else:
            # Linear default
            t = (x_gap - i0) / float(i1 - i0)
            arr[g_start : g_end + 1] = y0 + t * (y1 - y0)

    return arr


def gap_fill(
    data: np.ndarray,
    method: str = "linear",
    max_gap: int | None = None,
) -> np.ndarray:
    """Gap fill an array of shape (n_frames, ...) along axis 0."""
    arr = np.asarray(data, dtype=np.float64).copy()
    if arr.ndim == 1:
        return gap_fill_1d(arr, method=method, max_gap=max_gap)

    orig_shape = arr.shape
    flat = arr.reshape(orig_shape[0], -1)
    out = np.empty_like(flat)
    for c in range(flat.shape[1]):
        out[:, c] = gap_fill_1d(flat[:, c], method=method, max_gap=max_gap)
    return out.reshape(orig_shape)


def hampel_filter_1d(
    series: np.ndarray,
    window_size: int = 7,
    n_sigmas: float = 3.0,
) -> np.ndarray:
    """Detect and replace outlier spikes using Median Absolute Deviation (MAD).

    Matching `/home/preto/data/vaila/vaila/interp_smooth_split.py:hampel_filter`.
    """
    arr = np.asarray(series, dtype=np.float64).copy()
    n = len(arr)
    k = window_size // 2
    for i in range(n):
        if np.isnan(arr[i]):
            continue
        w = arr[max(0, i - k) : min(n, i + k + 1)]
        valid_w = w[~np.isnan(w)]
        if len(valid_w) < 3:
            continue
        med = float(np.median(valid_w))
        mad = float(1.4826 * np.median(np.abs(valid_w - med)))
        threshold = n_sigmas * mad if mad > 1e-9 else 1e-6

        if abs(arr[i] - med) > threshold:
            arr[i] = med
    return arr


def hampel_filter(
    data: np.ndarray,
    window_size: int = 7,
    n_sigmas: float = 3.0,
) -> np.ndarray:
    """Apply Hampel filter along axis 0 for multidimensional arrays."""
    arr = np.asarray(data, dtype=np.float64).copy()
    if arr.ndim == 1:
        return hampel_filter_1d(arr, window_size=window_size, n_sigmas=n_sigmas)
    orig_shape = arr.shape
    flat = arr.reshape(orig_shape[0], -1)
    out = np.empty_like(flat)
    for c in range(flat.shape[1]):
        out[:, c] = hampel_filter_1d(flat[:, c], window_size=window_size, n_sigmas=n_sigmas)
    return out.reshape(orig_shape)


def median_filter(
    data: np.ndarray,
    kernel_size: int = 5,
) -> np.ndarray:
    """Apply 1D median filter along axis 0."""
    if kernel_size % 2 == 0:
        kernel_size += 1
    arr = np.asarray(data, dtype=np.float64)
    filled = gap_fill(arr, method="nearest")
    if filled.ndim == 1:
        return medfilt(filled, kernel_size=kernel_size)
    orig_shape = filled.shape
    flat = filled.reshape(orig_shape[0], -1)
    out = np.empty_like(flat)
    for c in range(flat.shape[1]):
        out[:, c] = medfilt(flat[:, c], kernel_size=kernel_size)
    return out.reshape(orig_shape)


def moving_average(
    data: np.ndarray,
    window_size: int = 5,
) -> np.ndarray:
    """Apply symmetric moving average smoothing along axis 0."""
    if window_size < 2:
        return data.copy()
    arr = np.asarray(data, dtype=np.float64)
    filled = gap_fill(arr, method="nearest")
    kernel = np.ones(window_size, dtype=np.float64) / window_size

    def _ma_1d(s: np.ndarray) -> np.ndarray:
        pad_width = window_size // 2
        padded = np.pad(s, pad_width, mode="edge")
        conv = np.convolve(padded, kernel, mode="same")
        return conv[pad_width : len(s) + pad_width]

    if filled.ndim == 1:
        return _ma_1d(filled)
    orig_shape = filled.shape
    flat = filled.reshape(orig_shape[0], -1)
    out = np.empty_like(flat)
    for c in range(flat.shape[1]):
        out[:, c] = _ma_1d(flat[:, c])
    return out.reshape(orig_shape)


def butterworth_filter(
    data: np.ndarray,
    sample_rate: float,
    *,
    cutoff: float = 6.0,
    order: int = 4,
    padlen: int | None = None,
) -> np.ndarray:
    """Zero-lag low-pass Butterworth filter along axis 0.

    Dual-pass forward-backward (`filtfilt`) application with reflect-padding.
    Automatically gap-fills internal NaNs prior to filtering to prevent artifact explosion.
    """
    data_arr = np.asarray(data, dtype=np.float64)
    if data_arr.shape[0] < 10:
        return data_arr.copy()

    # Pre-fill gaps for continuous filtering
    nan_mask = np.isnan(data_arr)
    has_nans = np.any(nan_mask)
    work_data = gap_fill(data_arr, method="linear") if has_nans else data_arr

    nyquist = 0.5 * sample_rate
    normal_cutoff = cutoff / nyquist
    if not (0.0 < normal_cutoff < 1.0):
        raise ValueError(
            f"cutoff={cutoff} Hz is not valid for sample_rate={sample_rate} Hz "
            f"(normalized cutoff {normal_cutoff:.4f} must be in (0, 1))"
        )

    # Butterworth filter order for filtfilt: order//2 per pass makes net order = order
    filt_order = max(1, order // 2) if order > 1 else 1
    b, a = butter(filt_order, normal_cutoff, btype="low", analog=False)

    n_frames = work_data.shape[0]
    actual_pad = min(padlen if padlen is not None else 64, max(1, n_frames - 1))

    if work_data.ndim == 1:
        padded = np.pad(work_data, actual_pad, mode="reflect")
        filtered = filtfilt(b, a, padded)
        result = filtered[actual_pad:-actual_pad]
    else:
        orig_shape = work_data.shape
        flat = work_data.reshape(orig_shape[0], -1)
        padded = np.pad(flat, ((actual_pad, actual_pad), (0, 0)), mode="reflect")
        filtered = filtfilt(b, a, padded, axis=0)
        result = filtered[actual_pad:-actual_pad, :].reshape(orig_shape)

    return result


def process_marker_trial(
    trial: MarkerTrial,
    *,
    interp_method: str = "linear",
    max_gap: int | None = 10,
    smooth_method: str = "butterworth",
    cutoff_hz: float = 6.0,
    order: int = 4,
    window_size: int = 5,
    marker_labels: list[str] | None = None,
) -> MarkerTrial:
    """Execute gap filling and smoothing across MarkerTrial trajectories.

    Parameters:
        trial: source MarkerTrial.
        interp_method: 'none', 'linear', 'cubic', 'nearest'.
        max_gap: max gap size in frames to interpolate (None = no limit).
        smooth_method: 'none', 'butterworth', 'median', 'moving_average', 'hampel'.
        cutoff_hz: Butterworth cutoff frequency in Hz.
        order: Butterworth filter order (default 4 for 4th-order zero-phase).
        window_size: window size in frames for median, moving_average, or Hampel.
        marker_labels: subset of marker names to process. If None, processes all markers.
    """
    new_xyz = trial.xyz.copy()
    n_markers = trial.n_markers
    indices_to_process = (
        range(n_markers)
        if marker_labels is None
        else [trial.labels.index(lbl) for lbl in marker_labels if lbl in trial.labels]
    )

    for m in indices_to_process:
        marker_traj = new_xyz[:, m, :]  # shape (n_frames, 3)

        # 1. Spike / outlier removal before interpolation (if Hampel selected)
        if smooth_method == "hampel":
            marker_traj = hampel_filter(marker_traj, window_size=window_size)

        # 2. Gap Filling / Interpolation
        if interp_method not in ("none", "skip"):
            marker_traj = gap_fill(marker_traj, method=interp_method, max_gap=max_gap)

        # 3. Smoothing / Filtering
        if smooth_method == "butterworth":
            marker_traj = butterworth_filter(
                marker_traj,
                sample_rate=trial.rate_hz,
                cutoff=cutoff_hz,
                order=order,
            )
        elif smooth_method == "median":
            marker_traj = median_filter(marker_traj, kernel_size=window_size)
        elif smooth_method == "moving_average":
            marker_traj = moving_average(marker_traj, window_size=window_size)

        new_xyz[:, m, :] = marker_traj

    return MarkerTrial(
        labels=trial.labels,
        rate_hz=trial.rate_hz,
        xyz=new_xyz,
        residuals=trial.residuals.copy(),
    )
