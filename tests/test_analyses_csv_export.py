"""Unit tests for distance and angle analyses computation and CSV export."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from openbiomech.kinematic_analysis import (
    compute_distance_series,
    compute_vector_angle_series,
    export_analyses_csv,
    export_angle_csv,
    export_distance_csv,
)
from openbiomech.marker_trial import MarkerTrial


def create_synthetic_trial(n_frames: int = 10, rate_hz: float = 100.0) -> MarkerTrial:
    """Create a synthetic trial with predictable geometry for analysis testing."""
    labels = ("M_ORIGIN", "M_X", "M_Y", "M_Z", "M_DIAG")
    xyz = np.zeros((n_frames, len(labels), 3), dtype=np.float64)

    for f in range(n_frames):
        xyz[f, 0] = [0.0, 0.0, 0.0]  # M_ORIGIN
        xyz[f, 1] = [3.0, 0.0, 0.0]  # M_X: 3m along X
        xyz[f, 2] = [0.0, 4.0, 0.0]  # M_Y: 4m along Y
        xyz[f, 3] = [0.0, 0.0, 5.0]  # M_Z: 5m along Z
        xyz[f, 4] = [3.0, 4.0, 0.0]  # M_DIAG: hypot(3, 4) = 5m from origin

    # Insert a NaN gap at frame 3 for M_X if enough frames
    if n_frames > 3:
        xyz[3, 1] = [np.nan, np.nan, np.nan]

    return MarkerTrial(
        labels=labels,
        rate_hz=rate_hz,
        xyz=xyz,
        residuals=np.zeros((n_frames, len(labels))),
    )


def test_compute_distance_series():
    """Verify Euclidean distance computation across frames, including NaN gap handling."""
    trial = create_synthetic_trial(n_frames=10)
    # Distance between M_ORIGIN (0,0,0) and M_DIAG (3,4,0) should be 5.0 meters
    dist_origin_diag = compute_distance_series(trial, "M_ORIGIN", "M_DIAG")
    assert len(dist_origin_diag) == 10
    np.testing.assert_allclose(dist_origin_diag, 5.0)

    # Distance between M_ORIGIN and M_X has a NaN at frame 3
    dist_origin_x = compute_distance_series(trial, "M_ORIGIN", "M_X")
    assert np.isclose(dist_origin_x[0], 3.0)
    assert np.isnan(dist_origin_x[3])
    assert np.isclose(dist_origin_x[4], 3.0)


def test_export_distance_csv(tmp_path: Path):
    """Verify CSV formatting for distance series and file output."""
    trial = create_synthetic_trial(n_frames=5, rate_hz=50.0)
    out_file = tmp_path / "distance_test.csv"

    csv_text = export_distance_csv(trial, "M_ORIGIN", "M_X", filepath=out_file)
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == csv_text

    lines = [line.strip() for line in csv_text.strip().split("\n")]
    assert lines[0] == "frame,time_s,distance_m"
    assert lines[1] == "0,0.00000,3.000000"
    assert lines[2] == "1,0.02000,3.000000"
    # Frame 3 was NaN
    assert lines[4] == "3,0.06000,"


def test_compute_vector_angle_series_3pt():
    """Verify 3-point vertex angle calculation."""
    trial = create_synthetic_trial(n_frames=5)
    # Angle at M_ORIGIN between M_X and M_Y: X-axis vs Y-axis = 90 degrees
    angles_90 = compute_vector_angle_series(trial, "3pt", ("M_X", "M_ORIGIN", "M_Y"))
    assert np.isclose(angles_90[0], 90.0)
    # Frame 3 has M_X missing -> angle should be NaN
    assert np.isnan(angles_90[3])
    assert np.isclose(angles_90[4], 90.0)


def test_compute_vector_angle_series_4pt():
    """Verify 4-point (two independent vectors) angle calculation."""
    trial = create_synthetic_trial(n_frames=5)
    # Vector 1: M_ORIGIN -> M_X (along +X)
    # Vector 2: M_ORIGIN -> M_Z (along +Z)
    # Angle should be 90 degrees
    angles_4pt = compute_vector_angle_series(trial, "4pt", ("M_ORIGIN", "M_X", "M_ORIGIN", "M_Z"))
    assert np.isclose(angles_4pt[0], 90.0)
    assert np.isnan(angles_4pt[3])


def test_compute_vector_angle_series_abs():
    """Verify segment angle relative to global coordinate system axes."""
    trial = create_synthetic_trial(n_frames=5)
    # Segment M_ORIGIN -> M_Z is purely along +Z -> 0 degrees vs +Z
    ang_z = compute_vector_angle_series(trial, "abs", ("M_ORIGIN", "M_Z"), axis="+Z")
    assert np.isclose(ang_z[0], 0.0)

    # Segment M_ORIGIN -> M_X is along +X -> 90 degrees vs +Z
    ang_x_vs_z = compute_vector_angle_series(trial, "abs", ("M_ORIGIN", "M_X"), axis="+Z")
    assert np.isclose(ang_x_vs_z[0], 90.0)
    assert np.isnan(ang_x_vs_z[3])


def test_export_angle_csv(tmp_path: Path):
    """Verify angle CSV export content and formatting."""
    trial = create_synthetic_trial(n_frames=4, rate_hz=100.0)
    out_file = tmp_path / "angle_test.csv"

    csv_text = export_angle_csv(trial, "3pt", ("M_X", "M_ORIGIN", "M_Y"), filepath=out_file)
    assert out_file.exists()

    lines = [line.strip() for line in csv_text.strip().split("\n")]
    assert lines[0] == "frame,time_s,angle_deg"
    assert lines[1] == "0,0.00000,90.0000"
    assert lines[2] == "1,0.01000,90.0000"
    # Frame 3 is NaN
    assert lines[4] == "3,0.03000,"


def test_export_analyses_csv_combined(tmp_path: Path):
    """Verify combined analyses CSV export with both distance and angle columns."""
    trial = create_synthetic_trial(n_frames=4, rate_hz=100.0)
    out_file = tmp_path / "analyses_combined.csv"

    csv_text = export_analyses_csv(
        trial,
        distance_markers=("M_ORIGIN", "M_DIAG"),
        angle_def={"mode": "3pt", "markers": ("M_X", "M_ORIGIN", "M_Y")},
        filepath=out_file,
    )
    assert out_file.exists()

    lines = [line.strip() for line in csv_text.strip().split("\n")]
    assert lines[0] == "frame,time_s,distance_m,angle_deg"
    assert lines[1] == "0,0.00000,5.000000,90.000000"
    # Frame 3: distance is 5.0, but angle has NaN (M_X is missing)
    assert lines[4] == "3,0.03000,5.000000,"


def test_angle_mode_validation():
    """Verify ValueError is raised on mismatched marker count or unknown mode."""
    trial = create_synthetic_trial(n_frames=2)
    with pytest.raises(ValueError, match="3pt mode requires exactly 3 markers"):
        compute_vector_angle_series(trial, "3pt", ("M_X", "M_Y"))

    with pytest.raises(ValueError, match="4pt mode requires exactly 4 markers"):
        compute_vector_angle_series(trial, "4pt", ("M_X", "M_Y", "M_Z"))

    with pytest.raises(ValueError, match="Unsupported angle mode"):
        compute_vector_angle_series(trial, "unknown", ("M_X", "M_Y"))


def test_viewer_html_js_contract():
    """Verify that all new analysis export elements in viewer.html exist and are wired in viewer.js."""
    html_path = Path(__file__).resolve().parent.parent / "openbiomech" / "viewer.html"
    js_path = Path(__file__).resolve().parent.parent / "openbiomech" / "viewer.js"

    html_content = html_path.read_text(encoding="utf-8")
    js_content = js_path.read_text(encoding="utf-8")

    expected_ids = [
        "btn-distance-export-csv",
        "btn-angle-export-csv",
        "btn-export-plot1-csv",
        "btn-export-plot2-csv",
        "action-export-distance-csv",
        "action-export-angle-csv",
        "action-export-combined-analyses-csv",
        "action-export-plot",
    ]

    for element_id in expected_ids:
        assert f'id="{element_id}"' in html_content, f"Missing id in viewer.html: {element_id}"
        assert f'$("{element_id}")' in js_content, f"Missing handler in viewer.js for: {element_id}"

    # Verify export functions exist in viewer.js
    assert "function exportDistanceCsv()" in js_content
    assert "function exportAngleCsv()" in js_content
    assert "function exportCombinedAnalysesCsv()" in js_content
    assert "function exportPlotCsv(" in js_content
