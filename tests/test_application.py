"""Application tests: physical units, file commands and the local upload path."""

import json
import re
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import ezc3d
import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

from openbiomech.cli import main
from openbiomech.marker_trial import MarkerTrial
from openbiomech.trial_io import load_trial
from openbiomech.viewer import create_server, render_viewer, trial_payload


@pytest.mark.parametrize("units,scale", [("mm", 0.001), ("cm", 0.01), ("m", 1.0)])
def test_c3d_public_loader_normalizes_units(tmp_path, units, scale):
    c = ezc3d.c3d()
    c.add_parameter("POINT", "RATE", [100.0])
    c.add_parameter("POINT", "LABELS", ["p1", "p2"])
    c.add_parameter("POINT", "UNITS", [units])
    xyz = np.array(
        [[[0.0, 0.0, 0.0], [100.0, 200.0, 300.0]], [[1.0, 2.0, 3.0], [99.0, 198.0, 297.0]]]
    )
    c["data"]["points"] = np.concatenate([xyz.transpose(2, 1, 0), np.ones((1, 2, 2))])
    path = tmp_path / "units.c3d"
    c.write(str(path))
    assert_allclose(load_trial(path).xyz, xyz * scale)


def test_csv_units_rate_and_missing_columns(tmp_path, capsys):
    path = tmp_path / "markers.csv"
    path.write_text("frame,p1_x,p1_y,p1_z,p2_x,p2_y,p2_z\n0,0,0,0,300,400,0\n")
    trial = load_trial(path, rate_hz=240, units="mm")
    assert trial.rate_hz == 240
    assert_allclose(trial.xyz[0, 1], [0.3, 0.4, 0])
    assert main(["segment", str(path), "p1", "p2", "--rate", "240", "--units", "mm"]) == 0
    assert "0.5000 m" in capsys.readouterr().out
    path.write_text("frame,p1_x\n0,1\n")
    assert main(["info", str(path)]) == 1
    assert "missing coordinate columns" in capsys.readouterr().err
    with pytest.raises(ValueError, match="positive"):
        load_trial(path, rate_hz=0)


def test_dynamics_cli_round_trip_and_static_expected_loads(tmp_path):
    demo, output = tmp_path / "trial.json", tmp_path / "loads.csv"
    assert main(["demo", "--output", str(demo)]) == 0
    assert main(["dynamics", str(demo), "--output", str(output)]) == 0
    table = pd.read_csv(output)
    assert len(table) == 40
    for name, mass_below in [("foot", 1), ("shank", 4), ("thigh", 11), ("pelvis", 20)]:
        rows = table[table.segment == name]
        assert len(rows) == 10
        assert_allclose(rows.Fz_N, (mass_below - 20) * 9.80665, atol=1e-12)
        assert_allclose(rows[["Fx_N", "Fy_N", "Mx_Nm", "My_Nm", "Mz_Nm"]], 0, atol=1e-12)
        assert_allclose(rows.time_s, np.arange(10) / 100)


def test_invalid_dynamics_does_not_create_output_or_overwrite_input(tmp_path, capsys):
    path, output = tmp_path / "bad.json", tmp_path / "out.csv"
    path.write_text('{"schema_version": 1, "units": "mm"}')
    original = path.read_bytes()
    assert main(["dynamics", str(path), "-o", str(output)]) == 1
    assert "units='SI'" in capsys.readouterr().err
    assert not output.exists()
    assert main(["dynamics", str(path), "-o", str(path)]) == 1
    assert path.read_bytes() == original


def test_viewer_preserves_gaps_and_escapes_user_labels():
    label = "</script><script>throw new Error('injected')</script>"
    trial = MarkerTrial(
        (label,), 100, np.array([[[0, 1, 2]], [[np.nan, np.nan, np.nan]]]), np.zeros((2, 1))
    )
    payload = trial_payload(trial, label)
    html = render_viewer(payload)
    data = re.search(r'<script type="application/json" id="trial-data">(.*?)</script>', html, re.S)
    assert data is not None
    assert label not in data[1]
    recovered = json.loads(data[1])
    assert recovered["trial"]["labels"] == [label]
    assert recovered["trial"]["xyz"][1][0] == [None, None, None]
    assert "__VIEWER_SCRIPT__" not in html


def test_view_cli_exports_golden_trial(tmp_path):
    fixture = Path(__file__).parent.parent / "data/rec3d_20260826_121305_m.c3d"
    output = tmp_path / "motion.html"
    assert main(["view", str(fixture), "--output", str(output)]) == 0
    data = re.search(r'id="trial-data">(.*?)</script>', output.read_text(), re.S)
    assert data is not None
    payload = json.loads(data[1])
    assert not payload["server"]
    assert len(payload["trial"]["xyz"]) == 631
    assert len(payload["trial"]["labels"]) == 70


def test_local_gui_upload_matches_cli_and_rejects_missing_token(tmp_path):
    server, url = create_server()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    body = b"frame,p1_x,p1_y,p1_z\n0,1000,2000,3000\n"
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert b"mkvis3d" in response.read()
        connection.request("POST", "/api/trial?name=trial.csv", body=body)
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.request(
            "POST",
            "/api/trial?name=trial.csv&units=mm&rate=240",
            body=body,
            headers={"Authorization": f"Bearer {url.split('#')[1]}"},
        )
        response = connection.getresponse()
        assert response.status == 200
        payload = json.loads(response.read())
        path = tmp_path / "trial.csv"
        path.write_bytes(body)
        assert payload == trial_payload(load_trial(path, rate_hz=240, units="mm"), "trial.csv")
        connection.request(
            "POST",
            "/api/trial?name=bad.c3d",
            body=b"broken",
            headers={"Authorization": f"Bearer {url.split('#')[1]}"},
        )
        response = connection.getresponse()
        assert response.status == 400
        assert "error" in json.loads(response.read())

        # Test favicon.ico
        connection.request("GET", "/favicon.ico")
        response = connection.getresponse()
        assert response.status == 200
        assert b"PNG" in response.read() or len(response.read()) > 0

        # Test /api/current_trial
        connection.request("GET", "/api/current_trial")
        response = connection.getresponse()
        assert response.status == 200
        current_data = json.loads(response.read())
        assert current_data["name"] == "trial.csv"

        # Test /api/skeleton_templates
        connection.request("GET", "/api/skeleton_templates")
        response = connection.getresponse()
        assert response.status == 200
        templates_data = json.loads(response.read())
        assert "templates" in templates_data
        template_ids = [t["id"] for t in templates_data["templates"]]
        assert "sam3dinov3_mhr70" in template_ids

        # Test /api/skeleton_template?name=sam3dinov3_mhr70
        connection.request("GET", "/api/skeleton_template?name=sam3dinov3_mhr70")
        response = connection.getresponse()
        assert response.status == 200
        sam_data = json.loads(response.read())
        assert sam_data["num_keypoints"] == 70
        assert len(sam_data["connections"]) == 30

        # Test GET / retains active trial on reload/reflash
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        html_content = response.read().decode("utf-8")
        assert "trial.csv" in html_content
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cli_defaults_to_gui_when_no_args(monkeypatch):
    called = []

    def mock_serve_viewer(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr("openbiomech.viewer.serve_viewer", mock_serve_viewer)
    assert main(["gui", "--no-browser"]) == 0
    assert len(called) == 1
    assert called[0]["initial_trial"] is None


def test_browser_smoke_automated(tmp_path):
    import os
    import shutil
    import socket
    import subprocess
    import time
    import urllib.request

    node = shutil.which("node")
    chrome = shutil.which("google-chrome") or "/opt/google/chrome/chrome"
    if not node or not Path(chrome).exists():
        pytest.skip("node or chrome not installed")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        cdp_port = s.getsockname()[1]

    proc = subprocess.Popen(
        [
            chrome,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={tmp_path / 'chrome'}",
            f"--remote-debugging-port={cdp_port}",
            "--noerrdialogs",
            "--ozone-platform=headless",
            "--ozone-override-screen-size=1440,1050",
            "--use-angle=swiftshader-webgl",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    server, url = create_server(0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{cdp_port}/json/list", timeout=1
                ) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.fail("Chrome CDP did not become ready in time")

        root = Path(__file__).resolve().parent.parent
        env = dict(os.environ, CDP_PORT=str(cdp_port))
        res = subprocess.run(
            ["node", str(root / "tests/browser_smoke.mjs"), str(root), url],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"browser smoke failed: {res.stderr}\n{res.stdout}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
