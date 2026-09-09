"""Whole-body centre of mass from de Leva (1996) segment parameters.

Mass fractions and longitudinal segment CoM fractions are the adjusted
Zatsiorsky-Seluyanov values tabulated by de Leva, J. Biomech. 29(9),
1223-1230, DOI 10.1016/0021-9290(95)00178-6. Coordinates remain in the
input laboratory frame and precision remains float64.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

_MASS = {
    "female": {
        "head": 0.0668,
        "trunk": 0.4257,
        "upper_arm": 0.0255,
        "forearm": 0.0138,
        "hand": 0.0056,
        "thigh": 0.1478,
        "shank": 0.0481,
        "foot": 0.0129,
    },
    "male": {
        "head": 0.0694,
        "trunk": 0.4346,
        "upper_arm": 0.0271,
        "forearm": 0.0162,
        "hand": 0.0061,
        "thigh": 0.1416,
        "shank": 0.0433,
        "foot": 0.0137,
    },
}

_COM_FROM_PROXIMAL = {
    "female": {
        "head": 0.4841,
        "trunk": 0.4964,
        "upper_arm": 0.5754,
        "forearm": 0.4559,
        "hand": 0.7474,
        "thigh": 0.3612,
        "shank": 0.4352,
        "foot": 0.4014,
    },
    "male": {
        "head": 0.5002,
        "trunk": 0.5138,
        "upper_arm": 0.5772,
        "forearm": 0.4574,
        "hand": 0.7900,
        "thigh": 0.4095,
        "shank": 0.4395,
        "foot": 0.4415,
    },
}


def de_leva_mass_fraction(segment: str, sex: str) -> float:
    """Return segment mass divided by total body mass."""
    if sex not in _MASS:
        raise ValueError("sex must be 'female' or 'male'")
    if segment not in _MASS[sex]:
        raise ValueError(f"unknown de Leva segment {segment!r}")
    return _MASS[sex][segment]


def de_leva_com_fraction(segment: str, sex: str) -> float:
    """Return segment CoM fraction measured from its proximal endpoint."""
    if sex not in _COM_FROM_PROXIMAL:
        raise ValueError("sex must be 'female' or 'male'")
    if segment not in _COM_FROM_PROXIMAL[sex]:
        raise ValueError(f"unknown de Leva segment {segment!r}")
    return _COM_FROM_PROXIMAL[sex][segment]


def whole_body_com(
    segments: Mapping[str, tuple[np.ndarray, np.ndarray]],
    sex: str,
) -> np.ndarray:
    """Compute a mass-weighted whole-body CoM trajectory.

    ``segments`` maps names such as ``"trunk"``, ``"upper_arm_l"`` and
    ``"foot_r"`` to ``(proximal, distal)`` trajectories of shape
    ``(n_frames, 3)``. Side suffixes ``_l``/``_r`` are removed for de Leva
    lookup. Frames with a missing segment are renormalized over the available
    segment mass; frames with no valid segment return NaN.
    """
    if sex not in _MASS:
        raise ValueError("sex must be 'female' or 'male'")
    if not segments:
        raise ValueError("at least one segment trajectory is required")

    n_frames: int | None = None
    weighted: np.ndarray | None = None
    available_mass: np.ndarray | None = None
    for name, endpoints in segments.items():
        segment = name.removesuffix("_l").removesuffix("_r")
        if segment not in _MASS[sex]:
            raise ValueError(f"unknown de Leva segment {name!r}")
        proximal, distal = (np.asarray(value, dtype=np.float64) for value in endpoints)
        if proximal.ndim != 2 or proximal.shape[1:] != (3,) or distal.shape != proximal.shape:
            raise ValueError(f"{name} endpoints must both have shape (n_frames, 3)")
        if n_frames is None:
            n_frames = proximal.shape[0]
            weighted = np.zeros((n_frames, 3), dtype=np.float64)
            available_mass = np.zeros(n_frames, dtype=np.float64)
        elif proximal.shape[0] != n_frames:
            raise ValueError("all segment trajectories must have the same frame count")

        assert weighted is not None and available_mass is not None
        mass = _MASS[sex][segment]
        fraction = _COM_FROM_PROXIMAL[sex][segment]
        segment_com = proximal + fraction * (distal - proximal)
        valid = np.isfinite(segment_com).all(axis=1)
        weighted[valid] += mass * segment_com[valid]
        available_mass[valid] += mass

    assert weighted is not None and available_mass is not None
    result = np.full_like(weighted, np.nan)
    valid_frames = available_mass > 0
    result[valid_frames] = weighted[valid_frames] / available_mass[valid_frames, None]
    return result
