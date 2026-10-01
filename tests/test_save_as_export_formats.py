"""Tests for saving and exporting edited trials in C3D, CSV, 3D, and .vaila formats.

Verifies that after opening a .c3d or .vaila file and making modifications
(such as adding virtual points, center-of-mass landmarks, filtering, or gap-fills),
export and save-as operations produce valid, complete files across all supported formats.
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import numpy as np
import pytest
from numpy.testing import assert_allclose

from openbiomech.c3d_io import c3d_bytes, read_c3d_native, write_c3d
from openbiomech.marker_trial import MarkerTrial
from openbiomech.project_io import read_vaila_project, vaila_project_bytes
from openbiomech.trial_io import load_trial
from openbiomech.viewer import (
    create_server,
    export_stem,
    save_trial_files,
    trial_from_payload,
    trial_payload,
)


@pytest.fixture
def golden_c3d_path() -> Path:
    return Path(__file__).parent.parent / "data" / "rec3d_20260826_121305_m.c3d"


def test_write_c3d_with_template_after_adding_virtual_markers(golden_c3d_path, tmp_path):
    """Writing C3D with template must succeed when markers are added (virtual points/COM)."""
    original = load_trial(golden_c3d_path)
    template_bytes = golden_c3d_path.read_bytes()

    # Add virtual points and center-of-mass marker
    new_labels = (*original.labels, "Virtual_KJC", "CenterOfMass_deLeva_male")
    extra_coords = np.full((original.n_frames, 2, 3), 0.5, dtype=np.float64)
    new_xyz = np.concatenate([original.xyz, extra_coords], axis=1)
    new_residuals = np.zeros((original.n_frames, len(new_labels)), dtype=np.float64)

    edited_trial = MarkerTrial(
        labels=new_labels,
        rate_hz=original.rate_hz,
        xyz=new_xyz,
        residuals=new_residuals,
    )

    out_file = tmp_path / "edited_with_virtual.c3d"
    write_c3d(edited_trial, out_file, template=template_bytes)
    assert out_file.is_file()

    recovered = read_c3d_native(out_file)
    assert recovered.n_markers == len(new_labels)
    assert recovered.labels == new_labels
    assert recovered.n_frames == original.n_frames
    assert_allclose(recovered.xyz[:, -2:, :], extra_coords, atol=1e-5)


def test_write_c3d_with_template_after_deleting_markers(golden_c3d_path, tmp_path):
    """Writing C3D with template must succeed when markers are reduced."""
    original = load_trial(golden_c3d_path)
    template_bytes = golden_c3d_path.read_bytes()

    # Keep only first 5 markers
    kept_labels = original.labels[:5]
    kept_xyz = original.xyz[:, :5, :]
    edited_trial = MarkerTrial(
        labels=kept_labels,
        rate_hz=original.rate_hz,
        xyz=kept_xyz,
        residuals=np.zeros((original.n_frames, 5)),
    )

    out_file = tmp_path / "edited_reduced.c3d"
    write_c3d(edited_trial, out_file, template=template_bytes)
    recovered = read_c3d_native(out_file)
    assert recovered.n_markers == 5
    assert recovered.labels == kept_labels
    assert_allclose(recovered.xyz, kept_xyz, atol=1e-5)


def test_export_stem_strips_all_permitted_extensions():
    assert export_stem("subject_01.c3d") == "subject_01"
    assert export_stem("subject_01.csv") == "subject_01"
    assert export_stem("subject_01.3d") == "subject_01"
    assert export_stem("subject_01.vaila") == "subject_01"
    assert export_stem("/path/to/folder/gait_trial.vaila") == "gait_trial"
    assert export_stem("") == "trial"


def test_save_trial_files_all_permitted_formats(tmp_path):
    """save_trial_files supports c3d, csv, 3d, and vaila individually and combined."""
    xyz = np.array(
        [[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], [[1.1, 2.1, 3.1], [4.1, 5.1, 6.1]]],
        dtype=np.float64,
    )
    trial = MarkerTrial(
        labels=("M1", "M2"),
        rate_hz=100.0,
        xyz=xyz,
        residuals=np.zeros((2, 2)),
    )

    written = save_trial_files(
        trial,
        tmp_path,
        "sample",
        formats=("c3d", "csv", "3d", "vaila"),
        project_payload={
            "trial": trial_payload(trial, "sample"),
            "viewer_state": {"zoom": 1.5},
            "analyses": {},
        },
    )

    assert Path(written["c3d"]).is_file()
    assert Path(written["csv"]).is_file()
    assert Path(written["3d"]).is_file()
    assert Path(written["vaila"]).is_file()

    # Verify C3D
    c3d_trial = load_trial(written["c3d"])
    assert c3d_trial.labels == ("M1", "M2")
    assert_allclose(c3d_trial.xyz, xyz, atol=1e-5)

    # Verify CSV
    csv_trial = load_trial(written["csv"])
    assert csv_trial.labels == ("M1", "M2")
    assert_allclose(csv_trial.xyz, xyz, atol=1e-5)

    # Verify .3d
    p3d_trial = load_trial(written["3d"])
    assert p3d_trial.labels == ("M1", "M2")
    assert_allclose(p3d_trial.xyz, xyz, atol=1e-5)

    # Verify .vaila
    proj = read_vaila_project(Path(written["vaila"]))
    assert proj.viewer_state.get("zoom") == 1.5
    vaila_trial = trial_from_payload(proj.trial)
    assert vaila_trial.labels == ("M1", "M2")
    assert_allclose(vaila_trial.xyz, xyz, atol=1e-5)


def test_gui_save_as_after_modifying_vaila_project(tmp_path):
    """Opening a .vaila project, editing markers, and saving as C3D, CSV, or .3d."""
    source_dir = tmp_path / "source"
    chosen_dir = tmp_path / "export_dest"
    source_dir.mkdir()
    chosen_dir.mkdir()

    initial_xyz = np.array(
        [[[0.1, 0.2, 0.3]], [[0.4, 0.5, 0.6]]],
        dtype=np.float64,
    )
    initial_trial = MarkerTrial(("ORIG_M",), 120.0, initial_xyz, np.zeros((2, 1)))
    vaila_bytes = vaila_project_bytes(
        trial_payload(initial_trial, "initial.c3d"),
        {"theme": "dark"},
        {},
        source_name="initial.c3d",
        source_bytes=c3d_bytes(initial_trial),
    )
    vaila_file = source_dir / "project.vaila"
    vaila_file.write_bytes(vaila_bytes)

    # Start server simulating GUI with project loaded
    proj = read_vaila_project(vaila_file)
    payload = proj.trial

    # Simulate edits in GUI: add a virtual marker and change sampling rate
    payload["labels"] = ["ORIG_M", "VIRTUAL_PT"]
    payload["rate_hz"] = 60.0
    payload["xyz"] = [
        [[0.1, 0.2, 0.3], [1.0, 1.0, 1.0]],
        [[0.4, 0.5, 0.6], [2.0, 2.0, 2.0]],
    ]

    server, url = create_server(
        initial_payload=payload,
        initial_source_name=proj.source_name,
        initial_source_bytes=proj.source_bytes,
        source_dir=source_dir,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    token = url.split("#")[1]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        # 1. Save As C3D only
        conn.request(
            "POST",
            "/api/export/save_as",
            body=json.dumps(
                {"trial": payload, "directory": str(chosen_dir), "formats": ["c3d"], "filename": "new_run"}
            ).encode(),
            headers=headers,
        )
        resp = conn.getresponse()
        assert resp.status == 200
        res_data = json.loads(resp.read())
        saved_c3d = Path(res_data["c3d"])
        assert saved_c3d.name == "new_run.c3d"
        loaded = load_trial(saved_c3d)
        assert loaded.labels == ("ORIG_M", "VIRTUAL_PT")
        assert loaded.rate_hz == pytest.approx(60.0)

        # 2. Save As CSV only
        conn.request(
            "POST",
            "/api/export/save_as",
            body=json.dumps(
                {"trial": payload, "directory": str(chosen_dir), "formats": ["csv"], "filename": "new_run"}
            ).encode(),
            headers=headers,
        )
        resp2 = conn.getresponse()
        assert resp2.status == 200
        res_csv = json.loads(resp2.read())
        saved_csv = Path(res_csv["csv"])
        assert saved_csv.name == "new_run.csv"
        loaded_csv = load_trial(saved_csv)
        assert loaded_csv.labels == ("ORIG_M", "VIRTUAL_PT")
        assert loaded_csv.rate_hz == pytest.approx(60.0)

        # 3. Save As 3D only
        conn.request(
            "POST",
            "/api/export/save_as",
            body=json.dumps(
                {"trial": payload, "directory": str(chosen_dir), "formats": ["3d"], "filename": "new_run"}
            ).encode(),
            headers=headers,
        )
        resp3 = conn.getresponse()
        assert resp3.status == 200
        res_3d = json.loads(resp3.read())
        saved_3d = Path(res_3d["3d"])
        assert saved_3d.name == "new_run.3d"
        loaded_3d = load_trial(saved_3d)
        assert loaded_3d.labels == ("ORIG_M", "VIRTUAL_PT")

        # 4. Quick Save CSV endpoint (/api/export/csv) writes beside original file
        conn.request(
            "POST",
            "/api/export/csv",
            body=json.dumps({"trial": payload, "filename": "quick_saved.csv"}).encode(),
            headers=headers,
        )
        resp4 = conn.getresponse()
        assert resp4.status == 200
        csv_bytes = resp4.read()
        assert b"ORIG_M_x" in csv_bytes and b"VIRTUAL_PT_x" in csv_bytes
        assert (source_dir / "quick_saved.csv").is_file()

        # 5. Quick Save C3D endpoint (/api/export/c3d) with virtual markers writes beside source file
        conn.request(
            "POST",
            "/api/export/c3d",
            body=json.dumps({"trial": payload, "filename": "quick_saved.c3d"}).encode(),
            headers=headers,
        )
        resp5 = conn.getresponse()
        assert resp5.status == 200
        c3d_disk_path = source_dir / "quick_saved.c3d"
        assert c3d_disk_path.is_file()
        loaded_quick = load_trial(c3d_disk_path)
        assert loaded_quick.labels == ("ORIG_M", "VIRTUAL_PT")

    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
