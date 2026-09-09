"""Unit tests for C3D force platform extraction, calibration, and COP calculation.

Validates parity with C-Motion Visual3D and BTK Mokka on real force plate data.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from openbiomech.c3d_io import read_c3d_native
from openbiomech.viewer import trial_payload


@pytest.fixture
def squat_c3d() -> Path:
    p = Path("data/pilot0102_squat03.c3d")
    if not p.is_file():
        pytest.skip("data/pilot0102_squat03.c3d not found")
    return p


@pytest.fixture
def rec3d_c3d() -> Path:
    p = Path("data/rec3d_20260826_121305_m.c3d")
    if not p.is_file():
        pytest.skip("data/rec3d_20260826_121305_m.c3d not found")
    return p


def test_force_plates_extraction_squat(squat_c3d):
    trial = read_c3d_native(squat_c3d)

    assert trial.n_markers == 15
    assert trial.n_frames == 6772
    assert trial.rate_hz == 200.0

    # 2 active force platforms should be extracted (filtering out 2 zero-area dummy plates)
    assert len(trial.force_plates) == 2

    fp1 = trial.force_plates[0]
    fp2 = trial.force_plates[1]

    assert fp1.name == "FP1"
    assert fp1.plate_type == 2
    assert fp1.channels == (0, 1, 2, 3, 4, 5)

    assert fp2.name == "FP2"
    assert fp2.plate_type == 2
    assert fp2.channels == (12, 13, 14, 15, 16, 17)

    # Physical dimensions of 400mm x 600mm Bertec force plates
    corners1 = fp1.corners  # (4, 3)
    dim1_x = np.linalg.norm(corners1[1] - corners1[0])
    dim1_y = np.linalg.norm(corners1[3] - corners1[0])
    assert np.isclose(dim1_x, 0.4, atol=1e-3)
    assert np.isclose(dim1_y, 0.6, atol=1e-3)

    corners2 = fp2.corners
    dim2_x = np.linalg.norm(corners2[1] - corners2[0])
    dim2_y = np.linalg.norm(corners2[3] - corners2[0])
    assert np.isclose(dim2_x, 0.4, atol=1e-3)
    assert np.isclose(dim2_y, 0.6, atol=1e-3)


def test_force_plates_cop_and_grf_physics(squat_c3d):
    trial = read_c3d_native(squat_c3d)
    fp1, fp2 = trial.force_plates[0], trial.force_plates[1]

    # Active contact on all frames during squat
    assert fp1.contact.sum() == trial.n_frames
    assert fp2.contact.sum() == trial.n_frames

    # Ground Reaction Force vertical (Fz) must be positive upwards (3rd law reaction)
    fz1 = fp1.force[:, 2]
    fz2 = fp2.force[:, 2]
    assert (fz1 > 50.0).all(), f"FP1 Fz min = {fz1.min()}"
    assert (fz2 > 50.0).all(), f"FP2 Fz min = {fz2.min()}"

    # Sum of vertical forces reflects human bodyweight + barbell (~98 kg => ~966 N)
    total_fz = fz1 + fz2
    mean_bw = float(np.mean(total_fz))
    assert 850.0 < mean_bw < 1150.0, f"Mean total Fz = {mean_bw:.1f} N"

    # Center of Pressure (COP) must lie strictly within plate bounds under the feet
    # FP1 corners: X in [-0.4, 0.0], Y in [0.0, 0.6]
    cop1_x = fp1.cop[:, 0]
    cop1_y = fp1.cop[:, 1]
    assert np.all(cop1_x >= -0.4) and np.all(cop1_x <= 0.0)
    assert np.all(cop1_y >= 0.0) and np.all(cop1_y <= 0.6)

    # FP2 corners: X in [0.0, 0.4], Y in [0.0, 0.6]
    cop2_x = fp2.cop[:, 0]
    cop2_y = fp2.cop[:, 1]
    assert np.all(cop2_x >= 0.0) and np.all(cop2_x <= 0.4)
    assert np.all(cop2_y >= 0.0) and np.all(cop2_y <= 0.6)


def test_trial_without_force_plates(rec3d_c3d):
    trial = read_c3d_native(rec3d_c3d)
    assert len(trial.force_plates) == 0
    assert trial.n_markers == 70
    assert trial.n_frames == 631


def test_trial_payload_force_plates(squat_c3d):
    trial = read_c3d_native(squat_c3d)
    payload = trial_payload(trial, "squat_test")

    assert "force_plates" in payload
    assert len(payload["force_plates"]) == 2

    # Verify JSON serialization round-trip without allow_nan=True
    serialized = json.dumps(payload, allow_nan=False)
    decoded = json.loads(serialized)

    assert len(decoded["force_plates"]) == 2
    p1 = decoded["force_plates"][0]
    assert p1["name"] == "FP1"
    assert len(p1["corners"]) == 4
    assert len(p1["cop"]) == trial.n_frames
    assert len(p1["force"]) == trial.n_frames
