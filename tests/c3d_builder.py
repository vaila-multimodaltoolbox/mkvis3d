"""Minimal C3D *writer* used only by the tests.

The golden fixture in `data/` is a single Intel/float-format trial with no
analog channels, so it cannot exercise the 16-bit integer storage format, the
MIPS big-endian or DEC VAX processor flags, analog scaling, or invalid
(occluded) point residuals. This builder emits small synthetic files covering
those paths so the native reader can be checked against `ezc3d` — and, for the
VAX path that `ezc3d` does not read, against a round trip through this writer.

Deliberately test-only: it writes the smallest conforming file, not a
full-featured exporter, and lives outside `openbiomech/` so it can never be
mistaken for production code.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from openbiomech.c3d_io.binary_stream import DEC_VAX, MIPS

BLOCK_SIZE = 512


def float32_to_vax_f(values: np.ndarray) -> np.ndarray:
    """Encode IEEE-754 binary32 as VAX F-float bits (inverse of the reader).

    See `openbiomech.c3d_io.binary_stream.vax_f_to_float32`: the mantissa bits
    are identical and the exponent shifts by 2, then the two 16-bit halves are
    swapped relative to the IEEE layout.
    """
    ieee = np.asarray(values, dtype=np.float32).view(np.uint32)
    sign = (ieee >> 31) & 0x1
    exponent = (ieee >> 23) & 0xFF
    fraction = ieee & 0x7FFFFF

    vax_exponent = (exponent.astype(np.int64) + 2) & 0xFF
    word0 = (
        (sign.astype(np.uint32) << 15)
        | (vax_exponent.astype(np.uint32) << 7)
        | (fraction >> 16).astype(np.uint32)
    )
    word1 = (fraction & 0xFFFF).astype(np.uint32)
    bits = (word1 << 16) | word0
    bits = np.where(exponent == 0, np.uint32(0), bits).astype(np.uint32)
    return bits


@dataclass
class _Writer:
    processor: int

    @property
    def int_prefix(self) -> str:
        return ">" if self.processor == MIPS else "<"

    def u16(self, value: int) -> bytes:
        return struct.pack(f"{self.int_prefix}H", int(value) & 0xFFFF)

    def i16_array(self, values: np.ndarray) -> bytes:
        return np.asarray(values, dtype=f"{self.int_prefix}i2").tobytes()

    def f32(self, value: float) -> bytes:
        return self.f32_array(np.array([value], dtype=np.float32))

    def f32_array(self, values: np.ndarray) -> bytes:
        arr = np.asarray(values, dtype=np.float32)
        if self.processor == DEC_VAX:
            return float32_to_vax_f(arr).astype("<u4").tobytes()
        return arr.astype(f"{self.int_prefix}f4").tobytes()


@dataclass
class _Param:
    name: str
    group_id: int
    data_type: int
    dims: tuple[int, ...]
    payload: bytes


@dataclass
class C3DSpec:
    """What to synthesise. Coordinates are in the file's own units."""

    xyz: np.ndarray  # (n_frames, n_points, 3) float
    rate_hz: float = 100.0
    processor: int = 84
    point_scale: float = -1.0  # negative -> float storage, positive -> int16
    labels: tuple[str, ...] | None = None
    residual_words: np.ndarray | None = None  # (n_frames, n_points) int16, raw 4th word
    analog: np.ndarray | None = None  # (n_frames, n_subsamples, n_channels)
    analog_scale: np.ndarray | None = None
    analog_offset: np.ndarray | None = None
    analog_gen_scale: float = 1.0
    analog_labels: tuple[str, ...] = field(default_factory=tuple)

    @property
    def n_frames(self) -> int:
        return int(self.xyz.shape[0])

    @property
    def n_points(self) -> int:
        return int(self.xyz.shape[1])

    @property
    def n_subsamples(self) -> int:
        return 0 if self.analog is None else int(self.analog.shape[1])

    @property
    def n_channels(self) -> int:
        return 0 if self.analog is None else int(self.analog.shape[2])

    @property
    def is_float_format(self) -> bool:
        return self.point_scale < 0.0


def _group_record(w: _Writer, name: str, group_id: int, description: str = "") -> bytes:
    desc = description.encode("latin-1")
    payload = bytes([len(desc)]) + desc
    return (
        bytes([len(name)])
        + struct.pack("b", -group_id)
        + name.encode("latin-1")
        # The offset word follows the file's byte order like any other u16.
        + w.u16(2 + len(payload))
        + payload
    )


def _param_record(w: _Writer, p: _Param, description: str = "") -> bytes:
    desc = description.encode("latin-1")
    body = (
        struct.pack("b", p.data_type)
        + struct.pack("b", len(p.dims))
        + bytes(p.dims)
        + p.payload
        + bytes([len(desc)])
        + desc
    )
    return (
        bytes([len(p.name)])
        + struct.pack("b", p.group_id)
        + p.name.encode("latin-1")
        + w.u16(2 + len(body))
        + body
    )


def _char_param(name: str, group_id: int, values: tuple[str, ...]) -> _Param:
    width = max((len(v) for v in values), default=1) or 1
    payload = b"".join(v.ljust(width).encode("latin-1") for v in values)
    return _Param(name, group_id, -1, (width, len(values)), payload)


def _float_param(w: _Writer, name: str, group_id: int, values: np.ndarray) -> _Param:
    arr = np.atleast_1d(np.asarray(values, dtype=np.float32))
    return _Param(name, group_id, 4, (arr.size,), w.f32_array(arr))


def _int_param(w: _Writer, name: str, group_id: int, values: np.ndarray) -> _Param:
    arr = np.atleast_1d(np.asarray(values, dtype=np.int64))
    return _Param(name, group_id, 2, (arr.size,), w.i16_array(arr))


def build_c3d(spec: C3DSpec) -> bytes:
    """Serialise `spec` into a complete in-memory C3D file."""
    w = _Writer(spec.processor)
    labels = spec.labels or tuple(f"m{i + 1}" for i in range(spec.n_points))
    analog_labels = spec.analog_labels or tuple(f"a{i + 1}" for i in range(spec.n_channels))
    scales = (
        np.ones(spec.n_channels) if spec.analog_scale is None else np.asarray(spec.analog_scale)
    )
    offsets = (
        np.zeros(spec.n_channels) if spec.analog_offset is None else np.asarray(spec.analog_offset)
    )

    # --- parameter section -------------------------------------------------
    records = [_group_record(w, "POINT", 1), _group_record(w, "ANALOG", 2)]
    point_params = [
        _int_param(w, "USED", 1, np.array([spec.n_points])),
        _float_param(w, "SCALE", 1, np.array([spec.point_scale])),
        _float_param(w, "RATE", 1, np.array([spec.rate_hz])),
        _int_param(w, "FRAMES", 1, np.array([spec.n_frames])),
        _char_param("LABELS", 1, labels),
        _char_param("DESCRIPTIONS", 1, tuple("" for _ in labels)),
        _char_param("UNITS", 1, ("m",)),
    ]
    analog_params = [
        _int_param(w, "USED", 2, np.array([spec.n_channels])),
        _float_param(w, "RATE", 2, np.array([spec.rate_hz * max(spec.n_subsamples, 1)])),
        _float_param(w, "GEN_SCALE", 2, np.array([spec.analog_gen_scale])),
        _float_param(w, "SCALE", 2, scales if spec.n_channels else np.array([1.0])),
        # ANALOG:OFFSET is an integer parameter per the C3D spec; ezc3d rejects
        # the file outright if it is stored as a float.
        _int_param(w, "OFFSET", 2, offsets if spec.n_channels else np.array([0])),
        _char_param("LABELS", 2, analog_labels or ("",)),
        _char_param("DESCRIPTIONS", 2, tuple("" for _ in analog_labels) or ("",)),
        _char_param("UNITS", 2, tuple("V" for _ in analog_labels) or ("",)),
    ]
    for p in point_params + analog_params:
        records.append(_param_record(w, p))
    body = b"".join(records) + b"\x00\x00"  # 0-length label terminates the section

    n_param_blocks = max(1, (len(body) + 4 + BLOCK_SIZE - 1) // BLOCK_SIZE)
    parameters = bytes([1, 80, n_param_blocks, spec.processor]) + body
    parameters = parameters.ljust(n_param_blocks * BLOCK_SIZE, b"\x00")

    data_first_block = 2 + n_param_blocks

    # --- header block ------------------------------------------------------
    header = bytearray()
    header += bytes([2, 80])
    header += w.u16(spec.n_points)
    header += w.u16(spec.n_channels * spec.n_subsamples)
    header += w.u16(1)
    header += w.u16(spec.n_frames)
    header += w.u16(0)
    header += w.f32(spec.point_scale)
    header += w.u16(data_first_block)
    header += w.u16(spec.n_subsamples)
    header += w.f32(spec.rate_hz)
    header = header.ljust(BLOCK_SIZE, b"\x00")

    # --- data section ------------------------------------------------------
    words = (
        np.zeros((spec.n_frames, spec.n_points), dtype=np.int16)
        if spec.residual_words is None
        else np.asarray(spec.residual_words, dtype=np.int16)
    )
    scale = 1.0 if spec.is_float_format else abs(spec.point_scale)
    rows = []
    for f in range(spec.n_frames):
        block = np.empty(spec.n_points * 4, dtype=np.float64)
        block[0::4] = spec.xyz[f, :, 0] / scale
        block[1::4] = spec.xyz[f, :, 1] / scale
        block[2::4] = spec.xyz[f, :, 2] / scale
        block[3::4] = words[f, :]
        if spec.n_channels:
            block = np.concatenate([block, np.asarray(spec.analog)[f].ravel()])
        rows.append(block)
    flat = np.concatenate(rows) if rows else np.zeros(0)
    data = w.f32_array(flat) if spec.is_float_format else w.i16_array(np.rint(flat))
    pad = (-len(data)) % BLOCK_SIZE
    data = data + b"\x00" * pad

    return bytes(header) + parameters + data


def write_c3d(path: str | Path, spec: C3DSpec) -> Path:
    out = Path(path)
    out.write_bytes(build_c3d(spec))
    return out
