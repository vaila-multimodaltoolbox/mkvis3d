"""Golden-fixture test: the same real vailá `rec3d` trial, read from two
independent file formats (binary `.c3d` via ezc3d, wide `.csv`), must agree
on frame/marker counts, marker labels, and coordinates within tolerance.

This is the level-1 verifier that a future custom C3D parser
(`openbiomech.c3d_io.legacy_binary`) will also have to pass, per
`loops/openbiomech-python-prototype-loop.md` Phase 1.
"""

from __future__ import annotations

import numpy as np

from openbiomech.c3d_io import read_c3d
from openbiomech.csv_io import read_wide_csv

EXPECTED_N_FRAMES = 631
EXPECTED_N_MARKERS = 70
EXPECTED_RATE_HZ = 100.0


def test_c3d_header_matches_known_fixture_values(rec3d_c3d):
    trial = read_c3d(rec3d_c3d)
    assert trial.n_frames == EXPECTED_N_FRAMES
    assert trial.n_markers == EXPECTED_N_MARKERS
    assert trial.rate_hz == EXPECTED_RATE_HZ
    assert trial.labels == tuple(f"p{i}" for i in range(1, EXPECTED_N_MARKERS + 1))


def test_csv_matches_known_fixture_values(rec3d_csv):
    trial = read_wide_csv(rec3d_csv, rate_hz=EXPECTED_RATE_HZ)
    assert trial.n_frames == EXPECTED_N_FRAMES
    assert trial.n_markers == EXPECTED_N_MARKERS
    assert trial.labels == tuple(f"p{i}" for i in range(1, EXPECTED_N_MARKERS + 1))


def test_c3d_and_csv_agree_on_coordinates(rec3d_c3d, rec3d_csv):
    from_c3d = read_c3d(rec3d_c3d)
    from_csv = read_wide_csv(rec3d_csv, rate_hz=from_c3d.rate_hz)

    assert from_c3d.labels == from_csv.labels
    assert from_c3d.xyz.shape == from_csv.xyz.shape

    # Independently-produced numeric paths (DLT reconstruction -> CSV export
    # vs. -> C3D export) should match closely, not bit-exactly.
    diff = np.abs(from_c3d.xyz - from_csv.xyz)
    finite = np.isfinite(diff)
    assert finite.any(), "no finite/overlapping samples to compare"
    assert np.nanmax(diff[finite]) < 1e-3, (
        f"max |c3d - csv| = {np.nanmax(diff[finite])!r} exceeds 1e-3 (mm-level) tolerance"
    )
