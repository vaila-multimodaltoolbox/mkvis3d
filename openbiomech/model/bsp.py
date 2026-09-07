"""Body Segment Parameters (BSP), Dumas et al. 2007.

Source: R. Dumas, L. Cheze, J.-P. Verriest, "Adjustments to McConville et al.
and Young et al. body segment inertial parameters," J. Biomech. 40(3):543-553
(2007), plus its corrigendum (2007). Numeric values transcribed from the
secondary compilation Dumas & Wojtusch, 2018, "Estimation of the Body Segment
Inertial Parameters for the Rigid Body Biomechanical Models Used in Motion
Analysis," as tabulated in `Mass_fraction` / `Length_percent` in
`charlotte-lemouel/center_of_mass`'s `src/center_of_mass/kinematic.py`
(verified by direct `curl` of the raw file, cross-checked entry citations to
"Dumas et al., 2007a, Table 2").

Do NOT confuse this table with de Leva (1996) -- a distinct adjustment of
Zatsiorsky-Seluyanov data with materially different numeric values (e.g.
thigh male mass fraction 0.1416 for de Leva vs 0.123 here for Dumas). A
has-motion.com Visual3D wiki table was checked and rejected for this module
because its own text attributes it to de Leva (1996), not Dumas et al.
(2007).

Segment naming (no prior convention existed in this codebase --
`Segment.name` is a free-form string, e.g. "thigh_r"): keys here are
side-independent segment *types*, lowercase snake_case, matching the Dumas
table's own segment categories: "head", "torso" (combined thorax+abdomen,
Dumas et al. 2007a Table 2), "pelvis", "upper_arm", "forearm", "hand",
"thigh", "shank", "foot". BSP values are side-independent by definition, so
laterality (e.g. the "_r"/"_l" suffix on `Segment.name`) is not part of the
lookup key -- callers strip it before calling this module.

Implemented (this module):
    - `mass_fraction(segment, sex)`: segment mass as a fraction of total
      body mass.
    - `com_fraction_from_proximal(segment, sex)`: segment centre-of-mass
      location as a fraction of segment length, measured from the proximal
      end along the segment's longitudinal axis (i.e. directly usable with
      `Segment.longitudinal_axis`, which is already distal->proximal).
      Derived as `abs(y_s) / 100` from the Dumas table's Y-component
      (upward, local segment frame) of the CoM offset -- the only one of
      the three local-frame CoM axes (X=forward, Y=upward, Z=rightward)
      that maps cleanly onto mkvis3d's existing single-axis
      `Segment.longitudinal_axis` abstraction. Cross-checked against known
      literature figures (e.g. thigh CoM ~40% from proximal): consistent.

NOT implemented -- genuinely blocked, not guessed:
    - Anteroposterior (X) and mediolateral (Z) CoM offset components. The
      Dumas table gives a full 3D local-frame CoM offset, but mkvis3d does
      not yet have a full 3-axis anatomical segment coordinate system (only
      the single `longitudinal_axis`) needed to place these meaningfully.
      Same blocker class as the deferred per-joint anatomical JCS
      convention.
    - Radii of gyration / inertia tensor (`I_local`) for every segment. No
      reliably-sourced Dumas 2007 numeric values for these could be found
      or verified this session: absent from the has-motion.com page (which
      turned out to be de Leva 1996, not Dumas), and confirmed absent from
      `charlotte-lemouel/center_of_mass` (grepped its full Python source for
      "gyrat|inertia|Ixx|radi": zero matches). `newton_euler_step` therefore
      cannot be driven end-to-end from this module alone yet -- its
      `inertia_tensor` argument has no BSP-sourced value here.
"""

from __future__ import annotations

import numpy as np

# Exact x/y/z fallback fractions supplied in the continuation specification.
_DE_LEVA_RADII = {
    "thigh": (0.329, 0.329, 0.149),
    "shank": (0.255, 0.249, 0.103),
    "foot": (0.257, 0.245, 0.124),
}


def inertia_tensor(segment: str, mass_kg: float, length_m: float) -> np.ndarray:
    """CoM inertia (kg m²): diag(m * (r * L)**2), explicit de Leva fallback.

    Uses the exact radii requested in the 2026-09-07 continuation spec.
    Mass is segment mass, NOT body mass. Existing Dumas mass/CoM lookups
    remain separate; this is not a Dumas inertia tensor. The supplied
    profile has no sex split and covers thigh/shank/foot only. Pelvis
    inertia must be supplied separately. Local axes follow profile x/y/z.
    """
    if segment not in _DE_LEVA_RADII:
        raise ValueError(f"no de Leva fallback radii for {segment!r}; expected thigh, shank, foot")
    if not np.isfinite(mass_kg) or mass_kg <= 0:
        raise ValueError("mass_kg must be finite and positive")
    if not np.isfinite(length_m) or length_m <= 0:
        raise ValueError("length_m must be finite and positive")
    radii = np.asarray(_DE_LEVA_RADII[segment], dtype=np.float64)
    return np.diag(mass_kg * (radii * length_m) ** 2)


def global_inertia_tensor(local_inertia: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    """R @ I_com @ R.T; R columns are local axes expressed in the lab.

    Accepts constant (3,3) inertia and (...,3,3) rotations. Invalid frames,
    reflections and nonphysical inertia tensors raise ValueError.
    """
    inertia = np.asarray(local_inertia, dtype=np.float64)
    R = np.asarray(rotation, dtype=np.float64)
    if inertia.shape != (3, 3) or not np.isfinite(inertia).all():
        raise ValueError("local_inertia must be a finite (3, 3) tensor")
    if not np.allclose(inertia, inertia.T, atol=1e-12, rtol=0):
        raise ValueError("local_inertia must be symmetric")
    moments = np.linalg.eigvalsh(inertia)
    if moments[0] < 0 or moments[-1] > moments[0] + moments[1] + 1e-12:
        raise ValueError("local_inertia must have nonnegative physical principal moments")
    if R.ndim < 2 or R.shape[-2:] != (3, 3) or not np.isfinite(R).all():
        raise ValueError("rotation must have finite (..., 3, 3) matrices")
    if not np.allclose(R.swapaxes(-1, -2) @ R, np.eye(3), atol=1e-7, rtol=0) or not np.allclose(
        np.linalg.det(R), 1.0, atol=1e-7, rtol=0
    ):
        raise ValueError("rotation must be orthonormal and right-handed")
    return R @ inertia @ R.swapaxes(-1, -2)


_MASS_FRACTION: dict[str, dict[str, float]] = {
    "head": {"female": 0.067, "male": 0.067},
    "torso": {"female": 0.304, "male": 0.333},
    "pelvis": {"female": 0.147, "male": 0.142},
    "upper_arm": {"female": 0.023, "male": 0.024},
    "forearm": {"female": 0.014, "male": 0.017},
    "hand": {"female": 0.005, "male": 0.006},
    "thigh": {"female": 0.146, "male": 0.123},
    "shank": {"female": 0.045, "male": 0.048},
    "foot": {"female": 0.010, "male": 0.012},
}
"""Segment mass / total body mass. Dumas et al. 2007a Table 2 (via Dumas &
Wojtusch 2018). "torso" is the combined thorax+abdomen entry -- Dumas
separates Thorax (female 0.263, male 0.304) and Abdomen (female 0.041, male
0.029) individually, but mkvis3d has no separate thorax/abdomen segments, so
only the combined figure is exposed here."""

_COM_Y_PERCENT: dict[str, dict[str, float]] = {
    "head": {"female": 55.9, "male": 53.4},
    "torso": {"female": -43.6, "male": -42.0},
    "pelvis": {"female": -22.8, "male": -28.2},
    "upper_arm": {"female": -50.0, "male": -48.2},
    "forearm": {"female": -41.1, "male": -41.7},
    "hand": {"female": -76.8, "male": -83.9},
    "thigh": {"female": -37.7, "male": -42.9},
    "shank": {"female": -40.4, "male": -41.0},
    "foot": {"female": -30.9, "male": -19.9},
}
"""Raw Dumas `Length_percent` Y-component (upward, local segment frame,
percent of segment length), signed as published. Not for direct use --
`com_fraction_from_proximal` takes the absolute value (see module
docstring)."""


def _validate(segment: str, sex: str) -> None:
    if sex not in ("male", "female"):
        raise ValueError(f"unknown sex {sex!r}: expected 'male' or 'female'")
    if segment not in _MASS_FRACTION:
        raise ValueError(f"unknown segment {segment!r}: expected one of {sorted(_MASS_FRACTION)}")


def mass_fraction(segment: str, sex: str) -> float:
    """Segment mass as a fraction of total body mass (Dumas et al. 2007a).

    Args:
        segment: side-independent segment type, one of "head", "torso",
            "pelvis", "upper_arm", "forearm", "hand", "thigh", "shank",
            "foot".
        sex: "male" or "female".

    Returns:
        Mass fraction, dimensionless (segment mass / total body mass).

    Raises:
        ValueError: unknown segment or sex.
    """
    _validate(segment, sex)
    return _MASS_FRACTION[segment][sex]


def com_fraction_from_proximal(segment: str, sex: str) -> float:
    """Segment CoM location as a fraction of segment length from proximal.

    Derived from the Dumas table's local-frame Y (upward) CoM offset as
    `abs(y_s) / 100` (see module docstring for why only this axis is used).
    Directly usable as the fractional distance along `Segment.longitudinal_axis`
    (distal -> proximal) from the proximal end.

    Args:
        segment: side-independent segment type, same vocabulary as
            `mass_fraction`.
        sex: "male" or "female".

    Returns:
        Fraction in [0, 1] of segment length, measured from the proximal
        end.

    Raises:
        ValueError: unknown segment or sex.
    """
    _validate(segment, sex)
    return abs(_COM_Y_PERCENT[segment][sex]) / 100.0
