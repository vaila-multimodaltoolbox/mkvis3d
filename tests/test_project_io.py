"""Round-trip and safety tests for the open .vaila project format."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from openbiomech.project_io import read_vaila_project, vaila_project_bytes


def test_vaila_project_round_trip_preserves_trial_state_analyses_and_source():
    trial = {
        "name": "trial.c3d",
        "rate_hz": 120.0,
        "labels": ["p1"],
        "xyz": [[[1.0, 2.0, 3.0]]],
        "analog_labels": ["EMG"],
        "analog_rate_hz": 1200.0,
        "analog": [[[0.25], [0.5]]],
    }
    state = {
        "reference_system": {"ap": "+Y", "axial": "+Z"},
        "filter": {"smooth": "butterworth", "cutoff": 6.0},
        "skeleton_template": "sam3dinov3_mhr70",
    }
    analyses = {
        "distance": [{"markers": ["p1", "p2"], "values_m": [0.5]}],
        "orientations": [
            {
                "quaternion_convention": "wxyz",
                "quaternions": [[1.0, 0.0, 0.0, 0.0]],
                "euler": {"xyz": [[0.0, 0.0, 0.0]], "zyx": [[0.0, 0.0, 0.0]]},
            }
        ],
        "inverse_dynamics": [{"units": "SI", "loads": [[0.0, 0.0, 100.0]]}],
    }
    raw_source = b"synthetic C3D bytes"

    encoded = vaila_project_bytes(
        trial,
        state,
        analyses,
        source_name="original.c3d",
        source_bytes=raw_source,
    )
    recovered = read_vaila_project(encoded)

    assert encoded.startswith(b"PK")
    assert recovered.trial == trial
    assert recovered.viewer_state == state
    assert recovered.analyses == analyses
    assert recovered.source_name == "original.c3d"
    assert recovered.source_bytes == raw_source

    with zipfile.ZipFile(io.BytesIO(encoded)) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "trial.json",
            "viewer-state.json",
            "analyses.json",
            "source/original.c3d",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "vaila-project"
        assert manifest["schema_version"] == 1


def test_vaila_project_rejects_bad_zip_and_unsafe_source_name():
    with pytest.raises(ValueError, match="invalid .vaila"):
        read_vaila_project(b"not a zip")
    with pytest.raises(ValueError, match="named"):
        vaila_project_bytes({}, {}, {}, source_name="../bad.exe", source_bytes=b"x")


def test_vaila_project_detects_member_tampering():
    encoded = vaila_project_bytes({"xyz": []}, {}, {})
    source = zipfile.ZipFile(io.BytesIO(encoded))
    stream = io.BytesIO()
    with source, zipfile.ZipFile(stream, "w") as altered:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "trial.json":
                content = b'{"xyz":[1]}\n'
            altered.writestr(info.filename, content)

    with pytest.raises(ValueError, match="size mismatch|checksum mismatch"):
        read_vaila_project(stream.getvalue())
