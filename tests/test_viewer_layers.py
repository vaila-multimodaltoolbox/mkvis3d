"""Viewer layers: extra uploads that never replace the active trial, and the field reference."""

import json
from http.client import HTTPConnection
from threading import Thread

import numpy as np
import pytest
from numpy.testing import assert_allclose

from openbiomech.c3d_io import write_c3d
from openbiomech.marker_trial import MarkerTrial
from openbiomech.soccer_field.kiki49 import load_kiki49
from openbiomech.viewer import create_server, field_reference_payload, trial_payload


def _trial(offset: float, labels=("M1", "M2")) -> MarkerTrial:
    xyz = np.array([[[offset, 0.0, 0.0], [offset, 1.0, 0.0]]] * 3, dtype=np.float64)
    return MarkerTrial(labels=labels, rate_hz=60.0, xyz=xyz, residuals=np.zeros((3, 2)))


@pytest.fixture
def gui(tmp_path):
    base = _trial(0.0)
    base_bytes = write_c3d(base, tmp_path / "base.c3d").read_bytes()
    server, url = create_server(
        initial_payload=trial_payload(base, "base.c3d"),
        initial_source_name="base.c3d",
        initial_source_bytes=base_bytes,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    token = url.split("#")[1]

    def request(method, path, body=b"", content_type="application/octet-stream"):
        connection.request(
            method,
            path,
            body=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        )
        response = connection.getresponse()
        return response.status, response.read()

    try:
        yield request, tmp_path
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_field_reference_is_kiki49_world_frame():
    payload = field_reference_payload()
    field = load_kiki49()
    assert payload["labels"] == list(field.names)
    assert len(payload["xyz"]) == 1
    xyz = np.array(payload["xyz"][0], dtype=np.float64)
    assert_allclose(xyz, field.xyz)
    assert_allclose(xyz[payload["labels"].index("center_field")], [0.0, 0.0, 0.0])
    assert_allclose(np.abs(xyz[payload["labels"].index("top_left_corner")]), [52.45, 33.95, 0.0])


def test_layer_upload_keeps_active_trial_and_follows_active_c3d_template(gui):
    request, tmp_path = gui
    layer_bytes = write_c3d(_trial(5.0, ("L1", "L2")), tmp_path / "layer.c3d").read_bytes()

    status, body = request("POST", "/api/trial?name=layer.c3d&layer=1", layer_bytes)
    assert status == 200
    assert json.loads(body)["labels"] == ["L1", "L2"]
    status, body = request("GET", "/api/current_trial")
    assert json.loads(body)["name"] == "base.c3d"

    # Activation swaps the C3D export template to the newly active layer's bytes.
    status, body = request("POST", "/api/activate_layer?name=layer.c3d&from=base.c3d")
    assert (status, json.loads(body)) == (200, {"source": True})
    status, body = request("POST", "/api/activate_layer?name=base.c3d&from=layer.c3d")
    assert (status, json.loads(body)) == (200, {"source": True})
    status, body = request("POST", "/api/activate_layer?name=soccerfield_kiki49&from=base.c3d")
    assert (status, json.loads(body)) == (200, {"source": False})


def test_vaila_project_cannot_be_a_layer(gui):
    request, _ = gui
    status, body = request("POST", "/api/trial?name=p.vaila&layer=1", b"PK")
    assert status == 400
    assert "layer" in json.loads(body)["error"]


def test_field_reference_endpoint(gui):
    request, _ = gui
    status, body = request("GET", "/api/field_reference")
    assert status == 200
    assert json.loads(body)["name"] == "soccerfield_kiki49"
