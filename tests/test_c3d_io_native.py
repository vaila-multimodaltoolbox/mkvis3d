"""Phase-1 verifier: the from-scratch native C3D reader must agree with the
`ezc3d` oracle.

Two evidence sources, because the golden fixture alone cannot exercise the
whole format:

1. `data/rec3d_20260826_121305_m.c3d` — a real vailá `rec3d` trial (Intel,
   float storage, 70 markers, 631 frames, no analog). Parity here is the
   acceptance criterion of Phase 1 in
   `loops/openbiomech-python-prototype-loop.md`.
2. Synthetic files from `tests/c3d_builder.py` covering the branches the
   fixture does not reach: 16-bit integer storage, analog channels with
   per-channel scale/offset, occluded points, MIPS big-endian and DEC VAX.

`openbiomech.c3d_io.read_c3d` (the ezc3d wrapper) is the protected oracle and
is never modified to make the native reader agree.
"""

from __future__ import annotations

import numpy as np
import pytest
from c3d_builder import C3DSpec, float32_to_vax_f, write_c3d

from openbiomech.c3d_io import read_c3d, read_c3d_file, read_c3d_native
from openbiomech.c3d_io.binary_stream import C3DParseError, vax_f_to_float32
from openbiomech.c3d_io.parameters import Group, Parameter

TOLERANCE = 1e-3


def _param(group: Group, name: str) -> Parameter:
    """Fetch a parameter, failing the test loudly when the group lacks it."""
    found = group.get(name)
    assert found is not None, f"{group.name}:{name} missing from the parameter section"
    return found


# --------------------------------------------------------------------------
# 1. Golden fixture: native reader vs. the ezc3d oracle
# --------------------------------------------------------------------------


def test_native_header_matches_fixture(rec3d_c3d):
    parsed = read_c3d_file(rec3d_c3d)
    header = parsed.header

    assert header.processor == 84  # Intel little-endian
    assert header.n_points == 70
    assert header.first_frame == 1
    assert header.last_frame == 631
    assert header.n_frames == 631
    assert header.point_rate_hz == 100.0
    assert header.is_float_format  # POINT:SCALE is negative
    assert header.analog_samples_per_frame == 0
    assert header.n_analog_channels == 0
    assert header.data_first_block == 4


def test_native_parameter_section_matches_fixture(rec3d_c3d):
    groups = read_c3d_file(rec3d_c3d).groups

    assert {"POINT", "ANALOG"} <= set(groups)
    point = groups["POINT"]
    assert int(_param(point, "USED").value[0]) == 70
    assert float(_param(point, "RATE").value[0]) == 100.0
    assert float(_param(point, "SCALE").value[0]) == -1.0
    assert int(_param(point, "FRAMES").value[0]) == 631
    assert _param(point, "LABELS").value[:3] == ["p0", "p1", "p2"]
    assert len(_param(point, "LABELS").value) == 70
    assert int(_param(groups["ANALOG"], "USED").value[0]) == 0


def test_native_marker_data_matches_ezc3d_on_fixture(rec3d_c3d):
    oracle = read_c3d(rec3d_c3d)
    native = read_c3d_native(rec3d_c3d)

    assert native.labels == oracle.labels
    assert native.rate_hz == oracle.rate_hz
    assert native.xyz.shape == oracle.xyz.shape

    diff = np.abs(native.xyz - oracle.xyz)
    assert np.nanmax(diff) < TOLERANCE, f"max |native - ezc3d| = {np.nanmax(diff)!r}"
    assert np.nanmax(np.abs(native.residuals - oracle.residuals)) < TOLERANCE


def test_native_soa_layout_is_consistent_with_stacked_view(rec3d_c3d):
    points = read_c3d_file(rec3d_c3d).points

    assert points.x.shape == points.y.shape == points.z.shape == (631, 70)
    assert points.residual.shape == (631, 70)
    assert points.camera_mask.shape == (631, 70)
    stacked = points.as_xyz()
    assert stacked.shape == (631, 70, 3)
    assert np.array_equal(stacked[:, :, 1], points.y)


# --------------------------------------------------------------------------
# 2. Synthetic files: the branches the fixture cannot reach
# --------------------------------------------------------------------------


@pytest.fixture
def sample_xyz() -> np.ndarray:
    rng = np.random.default_rng(3)
    return rng.normal(size=(5, 4, 3)) * 100.0


def test_integer_storage_format_matches_ezc3d(tmp_path, sample_xyz):
    """POINT:SCALE > 0 -> coordinates stored as int16 and scaled on read."""
    scale = 0.1
    quantised = np.rint(sample_xyz / scale) * scale
    path = write_c3d(tmp_path / "int.c3d", C3DSpec(xyz=quantised, processor=84, point_scale=scale))

    native = read_c3d_native(path)
    oracle = read_c3d(path)

    assert not read_c3d_file(path).header.is_float_format
    assert np.nanmax(np.abs(native.xyz - oracle.xyz)) < TOLERANCE
    assert np.nanmax(np.abs(native.xyz - quantised)) < TOLERANCE


def test_analog_channels_match_ezc3d(tmp_path, sample_xyz):
    """Analog is scaled as (raw - OFFSET) * SCALE * GEN_SCALE, per channel."""
    rng = np.random.default_rng(11)
    analog = rng.normal(size=(5, 2, 4)) * 10.0  # 5 frames, 2 subsamples, 4 channels
    path = write_c3d(
        tmp_path / "analog.c3d",
        C3DSpec(
            xyz=sample_xyz,
            processor=84,
            point_scale=-1.0,
            analog=analog,
            analog_scale=np.array([1.0, 2.0, 0.5, 1.0]),
            analog_offset=np.array([0.0, 1.0, 3.0, 10.0]),
            analog_gen_scale=2.0,
        ),
    )

    parsed = read_c3d_file(path)
    assert parsed.header.n_analog_channels == 4
    assert parsed.header.analog_subsamples == 2
    assert parsed.analog.values.shape == (5, 2, 4)
    assert parsed.analog.rate_hz == 200.0
    assert parsed.analog.labels == ("a1", "a2", "a3", "a4")

    # ezc3d flattens to (1, n_channels, n_frames * n_subsamples).
    oracle = read_c3d(path)  # noqa: F841 - ensures the file loads cleanly in ezc3d too
    from ezc3d import c3d as _ezc3d

    expected = _ezc3d(str(path))["data"]["analogs"][0]
    assert np.max(np.abs(parsed.analog.flat().T - expected)) < TOLERANCE


def test_negative_analog_offset_is_signed(tmp_path, sample_xyz):
    """Deliberate divergence from the oracle, pinned so it cannot drift.

    `ezc3d` decodes a negative ANALOG:OFFSET as its magnitude; the C3D spec
    defines the offset as a signed integer, so the native reader subtracts it
    as written. Everything else about analog decoding matches ezc3d exactly
    (see `test_analog_channels_match_ezc3d`).
    """
    rng = np.random.default_rng(23)
    analog = rng.normal(size=(3, 1, 2)) * 10.0
    offsets = np.array([-4.0, 2.0])
    scales = np.array([1.0, 1.0])
    path = write_c3d(
        tmp_path / "negoff.c3d",
        C3DSpec(
            xyz=sample_xyz[:3],
            processor=84,
            point_scale=-1.0,
            analog=analog,
            analog_scale=scales,
            analog_offset=offsets,
            analog_gen_scale=1.0,
        ),
    )

    values = read_c3d_file(path).analog.values
    assert np.max(np.abs(values - (analog - offsets) * scales)) < TOLERANCE

    from ezc3d import c3d as _ezc3d

    oracle = _ezc3d(str(path))["data"]["analogs"][0]
    # Channel 1 (offset +2) agrees; channel 0 (offset -4) differs by 2*|offset|,
    # exactly the gap between subtracting -4 and subtracting +4.
    assert np.max(np.abs(values[:, :, 1].ravel() - oracle[1])) < TOLERANCE
    assert np.allclose(values[:, :, 0].ravel() - oracle[0], -2 * offsets[0], atol=TOLERANCE)


def test_residual_and_camera_mask_byte_roles(tmp_path, sample_xyz):
    """High byte = residual, low byte = camera mask, negative word = occluded.

    This is the mapping `ezc3d` uses; BTK's `ReadPoint` assigns the two bytes
    the other way round, so this test pins the choice down against the oracle
    rather than against the reference C++ source.
    """
    words = np.zeros((5, 4), dtype=np.int16)
    words[0, 0] = (5 << 8) | 1  # residual 5, camera 1
    words[0, 1] = 127  # residual 0, all 7 cameras
    words[0, 2] = 17 << 8  # residual 17, no cameras
    words[1, 0] = -1  # occluded
    path = write_c3d(
        tmp_path / "res.c3d",
        C3DSpec(xyz=sample_xyz, processor=84, point_scale=-1.0, residual_words=words),
    )

    points = read_c3d_file(path).points
    oracle = read_c3d(path)

    assert points.residual[0, 0] == 5.0
    assert points.camera_mask[0, 0] == 1
    assert points.residual[0, 1] == 0.0
    assert points.camera_mask[0, 1] == 127
    assert points.residual[0, 2] == 17.0
    assert points.camera_mask[0, 2] == 0

    # Occluded sample: residual -1 and NaN coordinates, exactly like ezc3d.
    assert points.residual[1, 0] == -1.0
    assert np.isnan(points.x[1, 0])
    assert np.isnan(oracle.xyz[1, 0, 0])
    assert np.array_equal(points.residual, oracle.residuals)


def test_mips_big_endian_round_trip(tmp_path, sample_xyz):
    """Processor 86 stores IEEE floats and integers big-endian.

    `ezc3d` raises `MIPS processor type not supported yet`, so the oracle here
    is the byte-level round trip through the builder rather than another
    reader.
    """
    path = write_c3d(tmp_path / "mips.c3d", C3DSpec(xyz=sample_xyz, processor=86, point_scale=-1.0))

    parsed = read_c3d_file(path)
    assert parsed.header.processor == 86
    assert parsed.byte_order.int_prefix == ">"
    assert parsed.header.n_points == 4
    assert parsed.point_labels == ("m1", "m2", "m3", "m4")
    assert np.nanmax(np.abs(parsed.points.as_xyz() - sample_xyz)) < TOLERANCE


def test_vax_float_round_trip(tmp_path, sample_xyz):
    """Processor 85 stores reals as VAX F-float (README.md §4.2).

    `ezc3d` cannot read this variant either, so correctness is established by
    the round trip plus the known-value bit patterns below.
    """
    path = write_c3d(tmp_path / "vax.c3d", C3DSpec(xyz=sample_xyz, processor=85, point_scale=-1.0))

    parsed = read_c3d_file(path)
    assert parsed.header.processor == 85
    assert parsed.byte_order.is_vax_float
    assert parsed.header.point_rate_hz == pytest.approx(100.0)
    assert np.nanmax(np.abs(parsed.points.as_xyz() - sample_xyz.astype(np.float32))) < TOLERANCE


def test_vax_f_float_known_bit_patterns():
    """Canonical VAX F-float encodings, decoded without hardware emulation."""
    # 1.0 -> sign 0, VAX exponent 129 (0x81), zero fraction => word0 = 0x4080.
    assert vax_f_to_float32(np.array([0x00004080], dtype=np.uint32))[0] == pytest.approx(1.0)
    # -1.0 sets the sign bit: word0 = 0xC080.
    assert vax_f_to_float32(np.array([0x0000C080], dtype=np.uint32))[0] == pytest.approx(-1.0)
    # A zero exponent is a true (or "dirty") zero.
    assert vax_f_to_float32(np.array([0x00000000], dtype=np.uint32))[0] == 0.0

    values = np.array([1.0, -1.0, 0.5, 123.456, -1e-3, 3.4e5], dtype=np.float32)
    assert np.allclose(vax_f_to_float32(float32_to_vax_f(values)), values, rtol=1e-6)


# --------------------------------------------------------------------------
# 3. Malformed input is rejected, not silently mis-decoded
# --------------------------------------------------------------------------


def test_rejects_bad_header_key(tmp_path, sample_xyz):
    raw = bytearray(write_c3d(tmp_path / "ok.c3d", C3DSpec(xyz=sample_xyz)).read_bytes())
    raw[1] = 0x51  # magic key must be 0x50
    bad = tmp_path / "bad_key.c3d"
    bad.write_bytes(raw)

    with pytest.raises(C3DParseError, match="header key"):
        read_c3d_file(bad)


def test_rejects_unknown_processor(tmp_path, sample_xyz):
    raw = bytearray(write_c3d(tmp_path / "ok2.c3d", C3DSpec(xyz=sample_xyz)).read_bytes())
    raw[512 + 3] = 99  # processor flag must be 84, 85 or 86
    bad = tmp_path / "bad_proc.c3d"
    bad.write_bytes(raw)

    with pytest.raises(C3DParseError, match="processor"):
        read_c3d_file(bad)


def test_rejects_truncated_file(tmp_path):
    bad = tmp_path / "short.c3d"
    bad.write_bytes(b"\x02\x50" + b"\x00" * 100)

    with pytest.raises(C3DParseError):
        read_c3d_file(bad)
