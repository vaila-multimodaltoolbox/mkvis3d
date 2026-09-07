"""Tests for the `openbiomech` CLI entry point (`openbiomech/cli.py`)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from openbiomech.cli import main

FIXTURE_C3D = Path(__file__).parent.parent / "data" / "rec3d_20260826_121305_m.c3d"
FIXTURE_CSV = Path(__file__).parent.parent / "data" / "rec3d_20260826_121305.csv"


def test_info_prints_trial_metadata_for_c3d(capsys):
    rc = main(["info", str(FIXTURE_C3D)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "frames:   631" in out
    assert "markers:  70" in out
    assert "rate:     100 Hz" in out
    assert "p1" in out and "p70" in out


def test_info_prints_trial_metadata_for_csv(capsys):
    rc = main(["info", str(FIXTURE_CSV)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "frames:   631" in out
    assert "markers:  70" in out


def test_segment_reports_length_and_axis(capsys):
    rc = main(["segment", str(FIXTURE_C3D), "p1", "p5"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "segment:      p1-p5" in out
    assert "length mean:" in out
    assert "axis (frame 0" in out


def test_unrecognized_extension_is_a_clean_error(capsys):
    rc = main(["info", "trial.xyz"])

    err = capsys.readouterr().err
    assert rc == 1
    assert "unrecognized extension" in err


def test_missing_file_is_a_clean_error(capsys, tmp_path):
    missing = tmp_path / "missing.c3d"

    rc = main(["info", str(missing)])

    err = capsys.readouterr().err
    assert rc == 1
    assert str(missing) in err


def test_no_command_exits_nonzero():
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_segment_matches_direct_model_computation():
    """Cross-check the CLI's printed mean length against Segment.length() directly."""
    from openbiomech.c3d_io import read_c3d_native
    from openbiomech.model import Segment, landmark_from_trial

    trial = read_c3d_native(FIXTURE_C3D)
    seg = Segment(
        name="p1-p5",
        proximal=landmark_from_trial(trial, "p1"),
        distal=landmark_from_trial(trial, "p5"),
    )
    expected_mean = np.nanmean(seg.length())

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["segment", str(FIXTURE_C3D), "p1", "p5"])
    assert rc == 0
    assert f"{expected_mean:.4f}" in buf.getvalue()
