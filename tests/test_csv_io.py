from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from openbiomech.csv_io import (
    _point_numbers_from_columns,
    read_wide_csv,
    write_wide_csv,
)
from openbiomech.marker_trial import MarkerTrial
from openbiomech.trial_io import load_trial

JJKABUTO_CSV = Path(
    "/home/preto/data/jjkabuto/JJ_Kabuto_sam3dinov3_visualized_id_00/JJ_Kabuto_id_00_mhr70_3d.csv"
)


def test_legacy_point_numbers_from_columns():
    cols = ["frame", "p1_x", "p1_y", "p1_z", "p10_x", "p10_y", "p10_z", "p2_x", "p2_y", "p2_z"]
    assert _point_numbers_from_columns(cols) == [1, 2, 10]


@pytest.mark.skipif(not JJKABUTO_CSV.exists(), reason="JJKabuto CSV fixture not available")
def test_read_wide_csv_jjkabuto_named_markers():
    trial = load_trial(JJKABUTO_CSV)
    assert trial.n_markers == 70
    assert trial.n_frames == 331
    assert trial.labels[0] == "nose"
    assert trial.labels[-1] == "neck"
    assert "left_shoulder" in trial.labels
    assert "right_shoulder" in trial.labels

    # Check numerical validity
    nose_coords = trial.marker("nose")
    assert nose_coords.shape == (331, 3)
    assert np.isclose(nose_coords[0, 0], 0.167732)
    assert np.isclose(nose_coords[0, 1], 0.020108)
    assert np.isclose(nose_coords[0, 2], 3.252952)


def test_read_wide_csv_formats():
    # 1. Underscores
    csv_under = "frame,nose_x,nose_y,nose_z,hip_x,hip_y,hip_z\n0,1.0,2.0,3.0,4.0,5.0,6.0\n1,1.1,2.1,3.1,4.1,5.1,6.1\n"
    trial1 = read_wide_csv(io.StringIO(csv_under))
    assert trial1.labels == ("nose", "hip")
    assert trial1.xyz.shape == (2, 2, 3)
    np.testing.assert_allclose(trial1.xyz[0, 0], [1.0, 2.0, 3.0])

    # 2. Dots and uppercase
    csv_dot = "Frame,C7.X,C7.Y,C7.Z,CLAV.X,CLAV.Y,CLAV.Z\n0,1,2,3,4,5,6\n"
    trial2 = read_wide_csv(io.StringIO(csv_dot))
    assert trial2.labels == ("C7", "CLAV")
    np.testing.assert_allclose(trial2.xyz[0, 0], [1.0, 2.0, 3.0])

    # 3. Colons (e.g. Vicon / Mokka / Subject-prefixed)
    csv_colon = "frame,Subject:R_Knee:x,Subject:R_Knee:y,Subject:R_Knee:z\n0,10,20,30\n"
    trial3 = read_wide_csv(io.StringIO(csv_colon))
    assert trial3.labels == ("Subject:R_Knee",)
    np.testing.assert_allclose(trial3.xyz[0, 0], [10.0, 20.0, 30.0])

    # 4. Spaces
    csv_space = "Frame,Left Ankle X,Left Ankle Y,Left Ankle Z\n0,1,2,3\n"
    trial4 = read_wide_csv(io.StringIO(csv_space))
    assert trial4.labels == ("Left Ankle",)
    np.testing.assert_allclose(trial4.xyz[0, 0], [1.0, 2.0, 3.0])

    # 5. Brackets
    csv_bracket = "time,LASI [X],LASI [Y],LASI [Z],RASI[x],RASI[y],RASI[z]\n0,1,2,3,4,5,6\n"
    trial5 = read_wide_csv(io.StringIO(csv_bracket))
    assert trial5.labels == ("LASI", "RASI")
    np.testing.assert_allclose(trial5.xyz[0, 1], [4.0, 5.0, 6.0])

    # 6. Semicolon delimiter
    csv_semi = "frame;p1_x;p1_y;p1_z;p2_x;p2_y;p2_z\n0;1;2;3;4;5;6\n"
    trial6 = read_wide_csv(io.StringIO(csv_semi))
    assert trial6.labels == ("p1", "p2")
    np.testing.assert_allclose(trial6.xyz[0, 0], [1.0, 2.0, 3.0])

    # 7. Tab delimiter
    csv_tab = "frame\tp1_x\tp1_y\tp1_z\n0\t1\t2\t3\n"
    trial7 = read_wide_csv(io.StringIO(csv_tab))
    assert trial7.labels == ("p1",)
    np.testing.assert_allclose(trial7.xyz[0, 0], [1.0, 2.0, 3.0])


def test_read_wide_csv_multiline_headers():
    csv_multi = """Frame,nose,,,left_eye,,
,X,Y,Z,X,Y,Z
0,0.1,0.2,0.3,0.4,0.5,0.6
1,0.2,0.3,0.4,0.5,0.6,0.7
"""
    trial = read_wide_csv(io.StringIO(csv_multi))
    assert trial.labels == ("nose", "left_eye")
    assert trial.n_frames == 2
    np.testing.assert_allclose(trial.xyz[0, 0], [0.1, 0.2, 0.3])
    np.testing.assert_allclose(trial.xyz[1, 1], [0.5, 0.6, 0.7])


def test_read_wide_csv_inferred_rate():
    # dt = 0.02s -> 50 Hz
    csv_time = "time,p1_x,p1_y,p1_z\n0.00,1,2,3\n0.02,1,2,3\n0.04,1,2,3\n"
    trial = read_wide_csv(io.StringIO(csv_time))
    assert np.isclose(trial.rate_hz, 50.0)

    # Explicit rate overrides
    trial_explicit = read_wide_csv(io.StringIO(csv_time), rate_hz=120.0)
    assert np.isclose(trial_explicit.rate_hz, 120.0)


def test_write_and_read_roundtrip(tmp_path: Path):
    labels = ("nose", "left_shoulder", "right_shoulder", "C7")
    n_frames = 10
    rng = np.random.default_rng(42)
    xyz = rng.standard_normal((n_frames, len(labels), 3))
    residuals = np.zeros((n_frames, len(labels)))

    orig_trial = MarkerTrial(labels=labels, rate_hz=60.0, xyz=xyz, residuals=residuals)
    csv_path = tmp_path / "test_roundtrip.csv"
    write_wide_csv(orig_trial, csv_path)

    loaded_trial = read_wide_csv(csv_path, rate_hz=60.0)
    assert loaded_trial.labels == orig_trial.labels
    assert loaded_trial.rate_hz == orig_trial.rate_hz
    np.testing.assert_allclose(loaded_trial.xyz, orig_trial.xyz)


def test_read_wide_csv_invalid_columns():
    csv_invalid = "frame,val1,val2,val3\n0,1,2,3\n"
    with pytest.raises(ValueError, match="no 3D marker coordinate triplets"):
        read_wide_csv(io.StringIO(csv_invalid))
