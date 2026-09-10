"""Unit tests for CSV marker trajectory import, export, replacement, and frame blanking."""

from __future__ import annotations

import numpy as np
import pytest

from openbiomech.kinematic_analysis import (
    add_marker_trajectory,
    blank_marker_frames,
    export_marker_trajectory_csv,
    load_marker_trajectory_csv,
    parse_frame_list_csv,
    replace_marker_trajectory,
)
from openbiomech.marker_trial import MarkerTrial


def make_test_trial(n_frames: int = 20) -> MarkerTrial:
    """Create a synthetic trial with 3 markers."""
    labels = ("M1", "M2", "M3")
    xyz = np.zeros((n_frames, len(labels), 3), dtype=np.float64)
    for f in range(n_frames):
        t = f * 0.01
        xyz[f, 0] = [1.0 + t, 2.0, 3.0]
        xyz[f, 1] = [4.0, 5.0 + t, 6.0]
        xyz[f, 2] = [7.0, 8.0, 9.0 + t]

    return MarkerTrial(
        labels=labels,
        rate_hz=100.0,
        xyz=xyz,
        residuals=np.zeros((n_frames, len(labels))),
    )


def test_parse_frame_list_csv():
    """Test parsing frame indices from various text/CSV layouts and ranges."""
    # Comma-separated with header
    csv_1 = "frame\n0\n1\n2\n5\n"
    assert parse_frame_list_csv(csv_1) == [0, 1, 2, 5]

    # Ranges and spaces
    csv_2 = "10-15, 20..22, 5"
    assert parse_frame_list_csv(csv_2) == [5, 10, 11, 12, 13, 14, 15, 20, 21, 22]

    # Semicolon and comments
    csv_3 = "# Frames to exclude\n1; 3; 7-9\n"
    assert parse_frame_list_csv(csv_3) == [1, 3, 7, 8, 9]


def test_load_marker_trajectory_csv_3_cols():
    """Test loading a 3-column CSV with x, y, z."""
    csv_text = """x, y, z
1.1, 2.2, 3.3
4.4, 5.5, 6.6
7.7, nan, 9.9
"""
    arr = load_marker_trajectory_csv(csv_text)
    assert arr.shape == (3, 3)
    np.testing.assert_allclose(arr[0], [1.1, 2.2, 3.3])
    np.testing.assert_allclose(arr[1], [4.4, 5.5, 6.6])
    assert arr[2, 0] == 7.7
    assert np.isnan(arr[2, 1])
    assert arr[2, 2] == 9.9


def test_load_marker_trajectory_csv_with_frame_time_and_semicolon():
    """Test loading a 5-column semicolon-separated CSV with frame, time, x, y, z."""
    csv_text = """frame;time_s;X;Y;Z
0;0.00000;1.000;2.000;3.000
1;0.01000;1.010;2.000;3.000
2;0.02000;1.020;2.000;3.000
"""
    arr = load_marker_trajectory_csv(csv_text)
    assert arr.shape == (3, 3)
    np.testing.assert_allclose(arr[0], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(arr[1], [1.01, 2.0, 3.0])
    np.testing.assert_allclose(arr[2], [1.02, 2.0, 3.0])


def test_load_marker_trajectory_csv_headerless_and_padding():
    """Test headerless 3-column CSV with expected_frames padding."""
    csv_text = """1.0 2.0 3.0
4.0 5.0 6.0
"""
    arr = load_marker_trajectory_csv(csv_text, expected_frames=5)
    assert arr.shape == (5, 3)
    np.testing.assert_allclose(arr[0], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(arr[1], [4.0, 5.0, 6.0])
    assert np.isnan(arr[2:]).all()


def test_export_and_load_roundtrip():
    """Test exporting a marker to CSV and loading it back."""
    trial = make_test_trial(15)
    csv_str = export_marker_trajectory_csv(trial, "M2")
    assert "frame,time_s,x,y,z" in csv_str

    reloaded = load_marker_trajectory_csv(csv_str)
    assert reloaded.shape == (15, 3)
    np.testing.assert_allclose(reloaded, trial.marker("M2"), atol=1e-5)


def test_replace_marker_trajectory():
    """Test replacing an existing marker's trajectory."""
    trial = make_test_trial(10)
    new_data = np.ones((10, 3), dtype=np.float64) * 42.0

    replace_marker_trajectory(trial, "M1", new_data)
    np.testing.assert_allclose(trial.marker("M1"), new_data)

    # Replaced marker with invalid shape should raise ValueError
    with pytest.raises(ValueError):
        replace_marker_trajectory(trial, "M1", np.ones((5, 3)))

    # Non-existent marker should raise ValueError
    with pytest.raises(ValueError):
        replace_marker_trajectory(trial, "UNKNOWN", new_data)


def test_add_marker_trajectory():
    """Test adding a new marker to a trial."""
    trial = make_test_trial(10)
    new_data = np.full((10, 3), 99.0, dtype=np.float64)

    add_marker_trajectory(trial, "M_NEW", new_data)
    assert "M_NEW" in trial.labels
    assert trial.n_markers == 4
    np.testing.assert_allclose(trial.marker("M_NEW"), new_data)

    # Adding duplicate marker should raise ValueError
    with pytest.raises(ValueError):
        add_marker_trajectory(trial, "M_NEW", new_data)


def test_blank_marker_frames():
    """Test blanking (setting to NaN) frames via list, range, and CSV."""
    trial = make_test_trial(20)

    # 1. Blank single frames
    blank_marker_frames(trial, "M1", frames=[2, 4])
    assert np.isnan(trial.marker("M1")[2]).all()
    assert np.isnan(trial.marker("M1")[4]).all()
    assert np.isfinite(trial.marker("M1")[3]).all()

    # 2. Blank frame range (inclusive)
    blank_marker_frames(trial, "M2", frame_range=(10, 14))
    for f in range(10, 15):
        assert np.isnan(trial.marker("M2")[f]).all()
    assert np.isfinite(trial.marker("M2")[9]).all()
    assert np.isfinite(trial.marker("M2")[15]).all()

    # 3. Blank via CSV source
    csv_frames = "frame\n0\n1\n18-19"
    blank_marker_frames(trial, "M3", csv_frames_source=csv_frames)
    assert np.isnan(trial.marker("M3")[0]).all()
    assert np.isnan(trial.marker("M3")[1]).all()
    assert np.isnan(trial.marker("M3")[18]).all()
    assert np.isnan(trial.marker("M3")[19]).all()
    assert np.isfinite(trial.marker("M3")[5]).all()
