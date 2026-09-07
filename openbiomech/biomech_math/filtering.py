"""4th-order zero-phase (dual-pass) Butterworth low-pass filter.

Ported from `/home/preto/data/vaila/vaila/filtering.py:apply_filter`
(the `method="butterworth"` branch only — the FIR branch is not part of
README.md's spec and is left out here), with the debug `print()`/`os.path`
calls removed.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt


def butterworth_filter(
    data: np.ndarray,
    sample_rate: float,
    *,
    cutoff: float = 6.0,
    order: int = 4,
    padlen: int = 128,
) -> np.ndarray:
    """Zero-lag low-pass filter `data` (n_frames, n_channels) along axis 0.

    Forward-backward (`filtfilt`) application of a Butterworth filter, with
    reflect-padding to reduce edge transients — see README.md §3.4.
    """
    data = np.asarray(data, dtype=np.float64)
    nyquist = 0.5 * sample_rate
    normal_cutoff = cutoff / nyquist
    if not (0.0 < normal_cutoff < 1.0):
        raise ValueError(
            f"cutoff={cutoff} Hz is not valid for sample_rate={sample_rate} Hz "
            f"(normalized cutoff {normal_cutoff} must be in (0, 1))"
        )

    b, a = butter(order, normal_cutoff, btype="low", analog=False)
    padded = np.pad(data, ((padlen, padlen), (0, 0)), mode="reflect")
    filtered = filtfilt(b, a, padded, axis=0)
    return filtered[padlen:-padlen, :]
