"""kiki49 geometry, YOLO-Pose label lines and keypoint completion."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")

from soccer_field_synth import HEIGHT, WIDTH, left_camera, projected_kiki  # noqa: E402

from openbiomech.soccer_field.camera import homography_from_camera  # noqa: E402
from openbiomech.soccer_field.kiki49 import AUX3D_POINTS, CSV_PATH, N_KPT, load_kiki49  # noqa: E402
from openbiomech.soccer_field.label_io import (  # noqa: E402
    format_label,
    parse_label,
    write_data_yaml,
)
from openbiomech.soccer_field.sample import (  # noqa: E402
    ORIGIN_ANNOTATED,
    ORIGIN_CAMERA,
    ORIGIN_NONE,
    ORIGIN_PLANE,
    complete_keypoints,
)

VAILA_CSV = Path("/home/preto/data/vaila/vaila/models/soccerfield_kiki.csv")


def test_flip_idx_is_an_x_mirror_involution() -> None:
    geo = load_kiki49()
    flip = np.array(geo.flip_idx)
    np.testing.assert_array_equal(flip[flip], np.arange(N_KPT))
    np.testing.assert_allclose(geo.xyz[flip], geo.xyz * [-1.0, 1.0, 1.0])


@pytest.mark.skipif(not VAILA_CSV.exists(), reason="vailá checkout not available")
def test_vendored_csv_matches_vaila() -> None:
    def rows(p: Path) -> list[dict[str, str]]:
        with p.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    assert rows(CSV_PATH) == rows(VAILA_CSV)


def test_label_round_trip_has_152_fields() -> None:
    kps = np.zeros((N_KPT, 3))
    kps[[0, 5, 48], :2] = [[100.5, 20.25], [640.0, 700.0], [1279.0, 360.0]]
    kps[[0, 5, 48], 2] = 2
    line = format_label(kps, WIDTH, HEIGHT)
    fields = line.split()
    assert len(fields) == 5 + 3 * N_KPT == 152
    assert fields[5 + 3 * 1 : 5 + 3 * 2] == ["0.000000", "0.000000", "0"]
    cx, cy, bw, bh = map(float, fields[1:5])
    assert (cx - bw / 2) * WIDTH == pytest.approx(100.5, abs=1e-3)
    assert (cy + bh / 2) * HEIGHT == pytest.approx(700.0, abs=1e-3)
    np.testing.assert_allclose(parse_label(line, WIDTH, HEIGHT), kps, atol=1e-3)
    with pytest.raises(ValueError):
        format_label(np.zeros((N_KPT, 3)), WIDTH, HEIGHT)


def test_data_yaml_describes_49_keypoints(tmp_path: Path) -> None:
    text = write_data_yaml(tmp_path).read_text()
    fields = dict(
        line.split(": ", 1)
        for line in text.splitlines()
        if ": " in line and not line.startswith(" ")
    )
    assert fields["kpt_shape"] == "[49, 3]"
    assert json.loads(fields["flip_idx"]) == list(load_kiki49().flip_idx)
    assert json.loads(fields["path"]) == str(tmp_path.resolve())


def test_complete_keypoints_fills_every_point_in_view() -> None:
    cam = left_camera()
    H = homography_from_camera(cam)
    uv, ok = projected_kiki(cam)
    aux = np.zeros(N_KPT, dtype=bool)
    aux[list(AUX3D_POINTS)] = True

    ann = np.zeros((N_KPT, 3))
    ann[1] = [uv[1, 0] + 1.5, uv[1, 1], 2]  # human click kept as clicked
    ann[2] = [-30.0, 100.0, 2]  # annotated outside the image: authoritative "not in view"
    kps, origin = complete_keypoints(ann, WIDTH, HEIGHT, H, cam, aux3d=True)

    assert origin[1] == ORIGIN_ANNOTATED and kps[1, 0] == pytest.approx(uv[1, 0] + 1.5)
    assert origin[2] == ORIGIN_NONE and not kps[2].any()
    plane = ok & ~aux & (np.arange(N_KPT) > 2)
    assert (origin[plane] == ORIGIN_PLANE).all()
    np.testing.assert_allclose(kps[plane, :2], uv[plane], atol=1e-6)
    assert (origin[ok & aux] == ORIGIN_CAMERA).all()
    assert not kps[~ok].any() and (origin[~ok] == ORIGIN_NONE).all()

    kps_no_aux, _ = complete_keypoints(ann, WIDTH, HEIGHT, H, cam, aux3d=False)
    assert not kps_no_aux[aux].any()
    np.testing.assert_array_equal(kps_no_aux[~aux], kps[~aux])
