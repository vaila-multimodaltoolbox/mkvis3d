"""Gait event detection (README.md's `events.rs`).

Implements the marker-only method of Zeni JA, Richards JG, Higginson JS,
"Two simple methods for determining gait events during treadmill and
overground walking using kinematic data", Gait & Posture 27(4), 2008 —
the standard reference for detecting heel-strike/toe-off without a force
plate. It is deliberately generic over which axis is "direction of
progression": the golden fixture's global frame orientation is whatever
the source `rec3d` DLT reconstruction used (`../../CLAUDE.md` §Data), not
re-derived here, so the axis is a caller-supplied index rather than a
hard-coded `X`/`Y`.

Method: a heel-strike is a local *maximum* and a toe-off a local *minimum*
of the (heel or toe marker) - (sacrum/pelvis reference marker) coordinate
along the progression axis. This module only needs two `Landmark`
trajectories and does not require knowing which one is anatomically
"heel" vs "toe" — call it twice with the two marker pairs of interest.

Force-plate-based event detection (README's "via GRF") is out of scope:
the golden fixture carries no analog/force channels
(`../../CLAUDE.md` §Data), and that path belongs with
`../inverse_dynamics/` once Phase 4 has a force-plate fixture.
"""

from __future__ import annotations

import numpy as np

from .landmark import Landmark


def _local_extrema(signal: np.ndarray, *, kind: str) -> np.ndarray:
    """Frame indices of local maxima (`kind="max"`) or minima (`kind="min"`).

    A strict local extremum: `signal[i]` strictly greater (max) or smaller
    (min) than both neighbours. NaN samples (occlusion) never compare
    true, so they are silently skipped rather than reported as events.
    """
    if kind not in ("max", "min"):
        raise ValueError(f"kind must be 'max' or 'min', got {kind!r}")
    if signal.ndim != 1:
        raise ValueError(f"expected a 1-D signal, got shape {signal.shape}")
    if signal.shape[0] < 3:
        return np.array([], dtype=np.int64)

    prev, curr, nxt = signal[:-2], signal[1:-1], signal[2:]
    mask = (curr > prev) & (curr > nxt) if kind == "max" else (curr < prev) & (curr < nxt)
    return np.flatnonzero(mask) + 1


def detect_gait_events(
    distal: Landmark, reference: Landmark, *, progression_axis: int
) -> dict[str, np.ndarray]:
    """Detect heel-strike/toe-off-style events from two marker trajectories.

    Args:
        distal: the moving marker of interest (e.g. a heel or toe marker).
        reference: a torso/pelvis marker approximating the body's forward
            translation (e.g. sacrum), so the signal reflects the limb's
            motion relative to the trunk rather than absolute lab position.
        progression_axis: index (0, 1, or 2) of the global axis along the
            direction of walking.

    Returns:
        `{"heel_strike": frame_indices, "toe_off": frame_indices}`, each a
        sorted `int64` array of local extrema of
        `distal[:, progression_axis] - reference[:, progression_axis]`
        (maxima = heel-strike, minima = toe-off, per Zeni et al. 2008).

    Raises:
        ValueError: mismatched shapes or an out-of-range axis.
    """
    if distal.positions.shape != reference.positions.shape:
        raise ValueError(
            f"landmark shapes must match: {distal.name} is {distal.positions.shape}, "
            f"{reference.name} is {reference.positions.shape}"
        )
    if progression_axis not in (0, 1, 2):
        raise ValueError(f"progression_axis must be 0, 1, or 2, got {progression_axis}")

    signal = distal.positions[:, progression_axis] - reference.positions[:, progression_axis]
    return {
        "heel_strike": _local_extrema(signal, kind="max"),
        "toe_off": _local_extrema(signal, kind="min"),
    }
