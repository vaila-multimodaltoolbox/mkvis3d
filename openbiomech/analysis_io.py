"""Explicit SI-unit JSON contract for reproducible inverse dynamics.

No marker-to-anatomy assignment is inferred. Inputs supply synchronized
segment poses, CoMs and derivatives, and a calibrated plate surface wrench.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .inverse_dynamics.chain import SegmentDynamics, inverse_dynamics_chain
from .inverse_dynamics.force_plate import global_plate_wrench
from .model.bsp import inertia_tensor


def run_dynamics(path: Path, output: Path) -> int:
    """Read schema version 1 and export one CSV row per frame and segment."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["schema_version"] != 1 or data["units"] != "SI":
            raise ValueError("dynamics requires schema_version=1 and units='SI'")
        rate = float(data["rate_hz"])
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("rate_hz must be finite and positive")
        segments = []
        for entry in data["segments"]:
            mass = float(entry["mass_kg"])
            if "inertia_com" in entry:
                inertia = np.asarray(entry["inertia_com"], dtype=np.float64)
            else:
                if entry["inertia_model"] != "de_leva_1996_fallback":
                    raise ValueError(
                        "inertia_model must be de_leva_1996_fallback or supply inertia_com"
                    )
                inertia = inertia_tensor(entry["segment_type"], mass, float(entry["length_m"]))
            segments.append(
                SegmentDynamics(
                    name=entry["name"],
                    mass_kg=mass,
                    inertia_com=inertia,
                    **{
                        key: np.asarray(entry[key], dtype=np.float64)
                        for key in (
                            "rotation",
                            "com",
                            "proximal",
                            "distal",
                            "com_acceleration",
                            "angular_velocity",
                            "angular_acceleration",
                        )
                    },
                )
            )
        plate = data["plate"]
        wrench = global_plate_wrench(
            plate["force"],
            plate["surface_moment"],
            plate["corners"],
            convention=plate["corner_convention"],
            f_threshold=float(plate.get("f_threshold", 15)),
        )
        result = inverse_dynamics_chain(segments, wrench["force"], wrench["moment"], wrench["cop"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"invalid dynamics JSON: {exc}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["frame", "time_s", "segment", "Fx_N", "Fy_N", "Fz_N", "Mx_Nm", "My_Nm", "Mz_Nm"]
        )
        for name, loads in result.items():
            for frame, (force, moment) in enumerate(
                zip(loads["force_proximal"], loads["moment_proximal"], strict=True)
            ):
                writer.writerow([frame, frame / rate, name, *force, *moment])
    return len(segments) * len(wrench["force"])


def write_demo(path: Path) -> None:
    """Create a four-segment static SI trial; pelvis inertia is synthetic."""
    n = 10
    data: dict = {
        "schema_version": 1,
        "units": "SI",
        "rate_hz": 100.0,
        "description": "Synthetic static chain; explicit masses and CoMs, NOT subject anthropometry.",
        "segments": [],
    }
    for i, (name, mass, length) in enumerate(
        [("foot", 1.0, 0.2), ("shank", 3.0, 0.4), ("thigh", 7.0, 0.4), ("pelvis", 9.0, 0.2)]
    ):
        distal = np.tile([0.0, 0.0, 0.3 * i], (n, 1))
        proximal = np.tile([0.0, 0.0, 0.3 * (i + 1)], (n, 1))
        entry = {
            "name": name,
            "mass_kg": mass,
            "com": ((distal + proximal) / 2).tolist(),
            "distal": distal.tolist(),
            "proximal": proximal.tolist(),
            "rotation": np.tile(np.eye(3), (n, 1, 1)).tolist(),
            **{
                key: np.zeros((n, 3)).tolist()
                for key in ("com_acceleration", "angular_velocity", "angular_acceleration")
            },
        }
        if name == "pelvis":
            entry["inertia_com"] = np.diag([0.1, 0.12, 0.15]).tolist()
        else:
            entry.update(inertia_model="de_leva_1996_fallback", segment_type=name, length_m=length)
        data["segments"].append(entry)
    data["plate"] = {
        "corner_convention": "continuation",
        "corners": [[0.5, 0.25, 0], [0.5, -0.25, 0], [-0.5, -0.25, 0], [-0.5, 0.25, 0]],
        "force": np.tile([0.0, 0.0, 20 * 9.80665], (n, 1)).tolist(),
        "surface_moment": np.zeros((n, 3)).tolist(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
