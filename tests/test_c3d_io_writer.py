"""Round-trip tests for edited C3D marker trajectory export."""

from __future__ import annotations

import numpy as np
from ezc3d import c3d
from numpy.testing import assert_allclose

from openbiomech.c3d_io import read_c3d_native, write_c3d
from openbiomech.marker_trial import MarkerTrial


def test_write_c3d_preserves_rate_labels_coordinates_and_gaps(tmp_path):
    xyz = np.array(
        [
            [[0.1, 0.2, 0.3], [1.0, 2.0, 3.0]],
            [[0.4, 0.5, 0.6], [np.nan, np.nan, np.nan]],
            [[0.7, 0.8, 0.9], [4.0, 5.0, 6.0]],
        ],
        dtype=np.float64,
    )
    trial = MarkerTrial(
        labels=("left", "right"),
        rate_hz=240.0,
        xyz=xyz,
        residuals=np.zeros((3, 2), dtype=np.float64),
    )

    output = write_c3d(trial, tmp_path / "edited.c3d")
    recovered = read_c3d_native(output)

    assert recovered.labels == trial.labels
    assert recovered.rate_hz == 240.0
    assert recovered.xyz.dtype == np.float64
    assert_allclose(recovered.xyz, xyz, atol=1e-7, equal_nan=True)


def test_write_c3d_preserves_synchronized_analog_channels(tmp_path):
    xyz = np.zeros((4, 1, 3), dtype=np.float64)
    analog = np.arange(4 * 5 * 2, dtype=np.float64).reshape(4, 5, 2) / 10
    trial = MarkerTrial(
        labels=("marker",),
        rate_hz=120.0,
        xyz=xyz,
        residuals=np.zeros((4, 1), dtype=np.float64),
        analog_labels=("Fx", "EMG"),
        analog_units=("N", "V"),
        analog_rate_hz=600.0,
        analog=analog,
    )

    recovered = read_c3d_native(write_c3d(trial, tmp_path / "analog.c3d"))

    assert recovered.rate_hz == 120.0
    assert recovered.analog_rate_hz == 600.0
    assert recovered.analog_labels == ("Fx", "EMG")
    assert recovered.analog_units == ("N", "V")
    assert recovered.analog.shape == (4, 5, 2)
    assert_allclose(recovered.analog, analog, atol=1e-7)


def test_write_c3d_template_preserves_unedited_parameter_groups(tmp_path):
    xyz = np.zeros((2, 1, 3), dtype=np.float64)
    trial = MarkerTrial(("m1",), 100.0, xyz, np.zeros((2, 1)))
    source = write_c3d(trial, tmp_path / "source.c3d")
    document = c3d(str(source))
    document.add_parameter("VAILA_TEST", "PROVENANCE", ["keep-me"])
    document.write(str(source))

    edited = MarkerTrial(("m1",), 120.0, xyz + 1.0, np.zeros((2, 1)))
    output = write_c3d(edited, tmp_path / "edited.c3d", template=source.read_bytes())
    recovered_document = c3d(str(output))

    assert recovered_document["parameters"]["VAILA_TEST"]["PROVENANCE"]["value"] == ["keep-me"]
    assert recovered_document["header"]["points"]["frame_rate"] == 120.0
    assert_allclose(read_c3d_native(output).xyz, edited.xyz)
