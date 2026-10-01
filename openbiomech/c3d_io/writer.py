"""C3D marker-trajectory writer backed by ezc3d.

The native reader remains the production parsing path.  Writing uses ezc3d
because it already handles the binary parameter and data-block layout across
C3D processor/storage variants and is a declared project dependency.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from ezc3d import c3d

from ..marker_trial import MarkerTrial


def write_c3d(
    trial: MarkerTrial,
    path: str | Path,
    *,
    template: str | Path | bytes | None = None,
) -> Path:
    """Write the current marker trajectories and sampling rate to a C3D file.

    Coordinates are stored in metres. Missing samples are encoded with a
    negative residual, as required by the C3D convention. Calibrated analog
    channels are retained with their point-frame synchronization.
    """
    output = Path(path)
    xyz = np.asarray(trial.xyz, dtype=np.float64)
    if xyz.ndim != 3 or xyz.shape != (trial.n_frames, trial.n_markers, 3):
        raise ValueError("trial.xyz must have shape (n_frames, n_markers, 3)")
    if not np.isfinite(trial.rate_hz) or trial.rate_hz <= 0:
        raise ValueError("trial rate must be finite and positive")
    if not trial.n_frames or not trial.n_markers or len(trial.labels) != trial.n_markers:
        raise ValueError("trial must contain frames and matching marker labels")

    points = np.zeros((4, trial.n_markers, trial.n_frames), dtype=np.float64)
    valid = np.isfinite(xyz).all(axis=2)
    points[:3] = np.where(valid[..., None], xyz, 0.0).transpose(2, 1, 0)

    residuals = np.asarray(trial.residuals, dtype=np.float64)
    if residuals.shape == valid.shape:
        stored_residuals = np.where(
            valid & np.isfinite(residuals), np.maximum(residuals, 0.0), -1.0
        )
    else:
        stored_residuals = np.where(valid, 0.0, -1.0)
    points[3] = stored_residuals.T

    template_directory: tempfile.TemporaryDirectory[str] | None = None
    try:
        if isinstance(template, bytes):
            template_directory = tempfile.TemporaryDirectory(prefix="openbiomech-template-")
            template_path = Path(template_directory.name) / "source.c3d"
            template_path.write_bytes(template)
            document = c3d(str(template_path))
        elif template is not None:
            document = c3d(str(template))
        else:
            document = c3d()
    except Exception:
        if template_directory is not None:
            template_directory.cleanup()
        raise
    document.add_parameter("POINT", "RATE", [float(trial.rate_hz)])
    document.add_parameter("POINT", "LABELS", list(trial.labels))
    document.add_parameter("POINT", "UNITS", ["m"])
    if (
        "POINT" in document.get("parameters", {})
        and "DESCRIPTIONS" in document["parameters"]["POINT"]
    ):
        old_desc = list(document["parameters"]["POINT"]["DESCRIPTIONS"].get("value", []))
        if len(old_desc) < trial.n_markers:
            old_desc.extend([""] * (trial.n_markers - len(old_desc)))
        elif len(old_desc) > trial.n_markers:
            old_desc = old_desc[: trial.n_markers]
        document.add_parameter("POINT", "DESCRIPTIONS", old_desc)

    document["data"]["points"] = points

    existing_meta = document["data"].get("meta_points")
    existing_masks = (
        existing_meta.get("camera_masks")
        if isinstance(existing_meta, dict) and "camera_masks" in existing_meta
        else None
    )
    if (
        isinstance(existing_masks, np.ndarray)
        and existing_masks.ndim == 3
        and existing_masks.shape[0] == 7
    ):
        camera_masks = np.zeros((7, trial.n_markers, trial.n_frames), dtype=bool)
        m_copy = min(trial.n_markers, existing_masks.shape[1])
        f_copy = min(trial.n_frames, existing_masks.shape[2])
        camera_masks[:, :m_copy, :f_copy] = existing_masks[:, :m_copy, :f_copy]
    else:
        camera_masks = np.zeros((7, trial.n_markers, trial.n_frames), dtype=bool)

    document["data"]["meta_points"] = {
        "residuals": stored_residuals.T[np.newaxis, ...],
        "camera_masks": camera_masks,
    }

    analog = np.asarray(trial.analog, dtype=np.float64)
    if analog.size:
        if analog.ndim != 3 or analog.shape[0] != trial.n_frames:
            raise ValueError("trial.analog must have shape (n_frames, n_subsamples, n_channels)")
        n_subsamples, n_channels = analog.shape[1:]
        if n_channels != len(trial.analog_labels):
            raise ValueError("analog channel count must match analog_labels")
        document.add_parameter("ANALOG", "RATE", [float(trial.rate_hz * n_subsamples)])
        document.add_parameter("ANALOG", "LABELS", list(trial.analog_labels))
        if trial.analog_units:
            if len(trial.analog_units) != n_channels:
                raise ValueError("analog channel count must match analog_units")
            document.add_parameter("ANALOG", "UNITS", list(trial.analog_units))
        document["data"]["analogs"] = analog.reshape(-1, n_channels).T[np.newaxis, ...]
    elif "ANALOG" in document.get("parameters", {}):
        # If template had analog parameters but edited trial has no analog data,
        # reset analog channels so ezc3d does not expect mismatched frame samples.
        document.add_parameter("ANALOG", "USED", [0])
        document.add_parameter("ANALOG", "RATE", [0.0])
        document["data"]["analogs"] = np.zeros((1, 0, 0), dtype=np.float64)

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            document.write(str(output))
        except Exception:
            if template is not None:
                # If template preservation failed, fall back to writing clean C3D
                return write_c3d(trial, output, template=None)
            raise
    finally:
        if template_directory is not None:
            template_directory.cleanup()
    return output


def c3d_bytes(trial: MarkerTrial, *, template: bytes | None = None) -> bytes:
    """Serialize a marker trial to C3D bytes."""
    with tempfile.TemporaryDirectory(prefix="openbiomech-c3d-") as directory:
        path = write_c3d(trial, Path(directory) / "trial.c3d", template=template)
        return path.read_bytes()
