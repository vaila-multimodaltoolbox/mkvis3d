"""Distal-to-proximal inverse dynamics of a synchronized rigid segment chain.

All kinematics are in the lab (metres, seconds, radians); rotations map
local inertia axes to lab axes. No anatomy is inferred from marker labels.
The caller supplies synchronized, filtered kinematics and explicit mass/CoM.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..model.bsp import global_inertia_tensor
from .newton_euler import newton_euler_step


@dataclass
class SegmentDynamics:
    """One rigid segment over N frames, ordered foot -> shank -> thigh -> pelvis.

    Vector fields have shape (N,3); rotation is (N,3,3); inertia_com is
    constant (3,3). com/proximal/distal are positions, not lever arms.
    Segment names are unique labels. Pelvis requires explicit inertia and
    a defined proximal boundary; this serial chain is not a bilateral model.
    """

    name: str
    mass_kg: float
    inertia_com: np.ndarray
    rotation: np.ndarray
    com: np.ndarray
    proximal: np.ndarray
    distal: np.ndarray
    com_acceleration: np.ndarray
    angular_velocity: np.ndarray
    angular_acceleration: np.ndarray


def inverse_dynamics_chain(
    segments: Sequence[SegmentDynamics],
    ground_force: np.ndarray,
    ground_moment: np.ndarray,
    cop: np.ndarray,
) -> dict[str, dict[str, np.ndarray]]:
    """Solve proximal reactions acting ON each segment, in distal-first order.

    Ground moment is the FREE moment applied at COP, from global_plate_wrench.
    Noncontact loads must already be zero (use its contact threshold). Output
    reactions are negated before application to the next proximal segment,
    by action/reaction. Copying the output without this sign change violates
    whole-chain momentum balance. No timestep differentiation is done here.
    """
    if not segments:
        raise ValueError("segments must contain at least one segment")
    force = np.asarray(ground_force, dtype=np.float64)
    moment = np.asarray(ground_moment, dtype=np.float64)
    point = np.asarray(cop, dtype=np.float64)
    shape = force.shape
    if force.ndim != 2 or shape[1] != 3 or shape[0] == 0:
        raise ValueError("ground_force must have nonempty (N, 3) shape")
    for name, array in (("ground_force", force), ("ground_moment", moment), ("cop", point)):
        if array.shape != shape or not np.isfinite(array).all():
            raise ValueError(f"{name} must have finite shape {shape}")
    result: dict[str, dict[str, np.ndarray]] = {}
    previous_joint = None
    for segment in segments:
        if not segment.name or segment.name in result:
            raise ValueError("segment names must be nonempty and unique")
        if not np.isfinite(segment.mass_kg) or segment.mass_kg <= 0:
            raise ValueError(f"{segment.name}: mass_kg must be finite and positive")
        vectors = {}
        for name in (
            "com",
            "proximal",
            "distal",
            "com_acceleration",
            "angular_velocity",
            "angular_acceleration",
        ):
            array = np.asarray(getattr(segment, name), dtype=np.float64)
            if array.shape != shape or not np.isfinite(array).all():
                raise ValueError(f"{segment.name}.{name} must have finite shape {shape}")
            vectors[name] = array
        R = np.asarray(segment.rotation, dtype=np.float64)
        if R.shape != (shape[0], 3, 3):
            raise ValueError(f"{segment.name}.rotation must have shape (N, 3, 3)")
        inertia = global_inertia_tensor(segment.inertia_com, R)
        if previous_joint is not None and not np.allclose(
            vectors["distal"], previous_joint, atol=1e-8, rtol=0
        ):
            raise ValueError(f"{segment.name}: adjacent joint centres do not coincide")
        loads = newton_euler_step(
            segment.mass_kg,
            vectors["com_acceleration"],
            inertia,
            vectors["angular_velocity"],
            vectors["angular_acceleration"],
            force,
            moment,
            vectors["proximal"] - vectors["com"],
            point - vectors["com"],
        )
        result[segment.name] = loads
        force = -loads["force_proximal"]
        moment = -loads["moment_proximal"]
        point = vectors["proximal"]
        previous_joint = point
    return result
