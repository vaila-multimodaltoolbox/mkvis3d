"""From-scratch native C3D binary reader (README.md §4).

Pure-Python/NumPy replacement for the `ezc3d` dependency, covering the
512-byte header block, the group/parameter section, and the 3D + analog data
section for all three processor architectures (Intel, DEC VAX, MIPS) in both
the 16-bit integer and 32-bit float storage formats.

Reverse-engineered against the Biomechanical ToolKit reference implementation
(`vendor/BTKCore/Code/IO/btkC3DFileIO.{h,cpp}`, `C3DFileIO::Read` and its
`Format` / `IntegerFormatSignedAnalog` / `FloatFormat` point readers) and
validated numerically against `ezc3d_reader.read_c3d` on the golden fixture
in `data/` — see `tests/test_c3d_io_native.py`.

Data is kept in a struct-of-arrays layout (`x`, `y`, `z`, `residual`,
`camera_mask` as separate contiguous arrays) per README.md §4.3, so the eventual
Rust port maps onto `Vec<f32>` fields directly and the arrays stay
vectorisation-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..marker_trial import MarkerTrial
from .binary_stream import ByteOrder, C3DParseError
from .header import BLOCK_SIZE, C3DHeader, parse_header
from .parameters import Group, parse_parameters


@dataclass
class PointData:
    """3D trajectories in struct-of-arrays layout.

    Every array is `(n_frames, n_points)`. Where a sample is flagged invalid
    (occluded/missing) `residual` is -1.0, per the C3D convention, and
    `x`/`y`/`z` are NaN. `camera_mask` holds the 7 camera-contribution bits.
    """

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    residual: np.ndarray
    camera_mask: np.ndarray

    @property
    def n_frames(self) -> int:
        return self.x.shape[0]

    @property
    def n_points(self) -> int:
        return self.x.shape[1]

    def as_xyz(self) -> np.ndarray:
        """Stack into a single `(n_frames, n_points, 3)` array-of-structs view."""
        return np.stack((self.x, self.y, self.z), axis=-1)


@dataclass
class AnalogData:
    """Analog channels, scaled to physical units.

    `values` is `(n_frames, n_subsamples, n_channels)`; `flat()` gives the
    contiguous `[frame][subsample][channel]` buffer described in README.md §4.3.
    """

    values: np.ndarray
    rate_hz: float
    labels: tuple[str, ...]

    @property
    def n_channels(self) -> int:
        return self.values.shape[2]

    def flat(self) -> np.ndarray:
        return self.values.reshape(-1, self.values.shape[2])


@dataclass
class C3DFile:
    """Everything decoded from one C3D file."""

    header: C3DHeader
    byte_order: ByteOrder
    groups: dict[str, Group]
    points: PointData
    analog: AnalogData
    point_labels: tuple[str, ...]


def _group_values(groups: dict[str, Group], group: str, parameter: str):
    grp = groups.get(group.upper())
    if grp is None:
        return None
    param = grp.get(parameter)
    return None if param is None else param.value


def _point_labels(groups: dict[str, Group], n_points: int) -> tuple[str, ...]:
    """Concatenate LABELS, LABELS2, ... and pad to `n_points`.

    Mirrors `ezc3d_reader._point_labels`; the continuation groups exist
    because a single parameter cannot exceed one 255-byte record dimension.
    """
    labels: list[str] = []
    values = _group_values(groups, "POINT", "LABELS")
    if values is not None:
        labels.extend(str(v) for v in values)
    suffix = 2
    while True:
        more = _group_values(groups, "POINT", f"LABELS{suffix}")
        if more is None:
            break
        labels.extend(str(v) for v in more)
        suffix += 1
    labels = labels[:n_points]
    while len(labels) < n_points:
        labels.append(f"uname*{len(labels) + 1}")
    return tuple(labels)


def _analog_labels(groups: dict[str, Group], n_channels: int) -> tuple[str, ...]:
    labels: list[str] = []
    values = _group_values(groups, "ANALOG", "LABELS")
    if values is not None:
        labels.extend(str(v) for v in values)
    labels = labels[:n_channels]
    while len(labels) < n_channels:
        labels.append(f"uname*{len(labels) + 1}")
    return tuple(labels)


def _channel_vector(raw, n_channels: int, default: float) -> np.ndarray:
    """Broadcast a per-channel parameter to length `n_channels`."""
    out = np.full(n_channels, float(default), dtype=np.float64)
    if raw is None:
        return out
    values = np.atleast_1d(np.asarray(raw, dtype=np.float64)).ravel()
    take = min(n_channels, values.size)
    out[:take] = values[:take]
    return out


def _split_residual_word(
    words: np.ndarray, point_scale: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode the 4th point word into (residual, camera_mask, invalid).

    The word's **low** byte carries the camera-contribution bits (one per
    camera, 7 of them) and the **high** byte carries the reconstruction
    residual in units of |POINT:SCALE|. A negative word (0xFFFF) flags a
    missing/occluded measurement: residual becomes -1 and the coordinates are
    meaningless.

    BTK's `IntegerFormatSignedAnalog::ReadPoint` / `FloatFormat::ReadPoint`
    assign the two bytes the other way round; `ezc3d` — this project's
    declared oracle, and the reader vailá already uses in production — uses
    the mapping implemented here, and it is the one the C3D manual describes.
    Verified empirically against `ezc3d` in
    `tests/test_c3d_io_native.py::test_residual_and_camera_mask_byte_roles`.
    """
    as_int = words.astype(np.int32)
    invalid = as_int < 0
    residual = ((as_int >> 8) & 0xFF).astype(np.float64) * abs(point_scale)
    residual[invalid] = -1.0
    camera_mask = (as_int & 0x7F).astype(np.uint16)
    camera_mask[invalid] = 0
    return residual, camera_mask, invalid


def _read_data_section(
    buf: bytes, header: C3DHeader, order: ByteOrder, groups: dict[str, Group]
) -> tuple[PointData, AnalogData]:
    n_points = header.n_points
    n_channels = header.n_analog_channels
    n_sub = header.analog_subsamples if n_channels else 0
    values_per_frame = n_points * 4 + n_sub * n_channels

    start = BLOCK_SIZE * (header.data_first_block - 1)
    if start >= len(buf) and values_per_frame:
        raise C3DParseError("Data section starts past the end of the file")

    item_bytes = 4 if header.is_float_format else 2
    available = max(len(buf) - start, 0)
    n_frames = header.n_frames
    if values_per_frame:
        fits = available // (values_per_frame * item_bytes)
        if fits < n_frames:
            # Header frame count disagrees with the bytes actually present
            # (truncated file, or a >65535-frame trial whose real count lives
            # in POINT:FRAMES). Decode what is there rather than over-reading.
            n_frames = int(fits)

    total = values_per_frame * n_frames
    if header.is_float_format:
        raw = order.f32_array(buf, start, total).astype(np.float64)
    else:
        raw = order.i16_array(buf, start, total).astype(np.float64)
    raw = raw.reshape(n_frames, values_per_frame) if n_frames else raw.reshape(0, values_per_frame)

    point_block = raw[:, : n_points * 4].reshape(n_frames, n_points, 4)
    scale = abs(header.point_scale) if not header.is_float_format else 1.0
    x = np.ascontiguousarray(point_block[:, :, 0] * scale)
    y = np.ascontiguousarray(point_block[:, :, 1] * scale)
    z = np.ascontiguousarray(point_block[:, :, 2] * scale)
    # The residual word is stored as a real in float files; round-trip it back
    # through int16 exactly as BTK does before splitting the two bytes.
    words = point_block[:, :, 3].astype(np.int32).astype(np.int16)
    residual, camera_mask, invalid = _split_residual_word(words, header.point_scale)
    # Occluded samples carry no usable coordinates; NaN them out so callers
    # cannot mistake the placeholder for a measurement (same as `ezc3d`).
    x[invalid] = np.nan
    y[invalid] = np.nan
    z[invalid] = np.nan
    points = PointData(x=x, y=y, z=z, residual=residual, camera_mask=camera_mask)

    if n_channels:
        # (raw - OFFSET) * SCALE * GEN_SCALE, per BTK's analog read loop.
        # Known divergence: `ezc3d` uses |OFFSET|, so a *negative* ANALOG:OFFSET
        # decodes differently there. We keep the signed value the C3D spec
        # defines; pinned by
        # `tests/test_c3d_io_native.py::test_negative_analog_offset_is_signed`.
        analog_raw = raw[:, n_points * 4 :].reshape(n_frames, n_sub, n_channels)
        offsets = _channel_vector(_group_values(groups, "ANALOG", "OFFSET"), n_channels, 0.0)
        if not header.is_float_format:
            fmt = _group_values(groups, "ANALOG", "FORMAT")
            if fmt and str(np.atleast_1d(fmt)[0]).upper().startswith("UNSIGNED"):
                offsets = np.asarray(offsets, dtype=np.int64).astype(np.uint16).astype(np.float64)
        scales = _channel_vector(_group_values(groups, "ANALOG", "SCALE"), n_channels, 1.0)
        gen_raw = _group_values(groups, "ANALOG", "GEN_SCALE")
        gen_scale = float(np.atleast_1d(gen_raw)[0]) if gen_raw is not None else 1.0
        if gen_scale == 0.0:
            gen_scale = 1.0
        analog_values = (analog_raw - offsets) * scales * gen_scale
    else:
        analog_values = np.zeros((n_frames, 0, 0), dtype=np.float64)

    analog = AnalogData(
        values=analog_values,
        rate_hz=header.point_rate_hz * max(n_sub, 1),
        labels=_analog_labels(groups, n_channels),
    )
    return points, analog


def read_c3d_file(path: str | Path) -> C3DFile:
    """Fully decode a C3D file: header, parameters, points and analog."""
    buf = Path(path).read_bytes()
    header, order = parse_header(buf)
    groups = parse_parameters(buf, header.parameter_first_block, order)
    points, analog = _read_data_section(buf, header, order, groups)
    return C3DFile(
        header=header,
        byte_order=order,
        groups=groups,
        points=points,
        analog=analog,
        point_labels=_point_labels(groups, header.n_points),
    )


def read_c3d(path: str | Path) -> MarkerTrial:
    """Read marker trajectories from a C3D file without the `ezc3d` dependency.

    Drop-in replacement for `ezc3d_reader.read_c3d`; the two are asserted to
    agree on the golden fixture in `tests/test_c3d_io_native.py`.
    """
    parsed = read_c3d_file(path)
    used = _group_values(parsed.groups, "POINT", "USED")
    n_used = int(np.atleast_1d(used)[0]) if used is not None else parsed.header.n_points

    if n_used <= 0 or not parsed.point_labels:
        return MarkerTrial(
            labels=(),
            rate_hz=float(parsed.header.point_rate_hz),
            xyz=np.zeros((0, 0, 3), dtype=np.float64),
            residuals=np.zeros((0, 0), dtype=np.float64),
        )

    return MarkerTrial(
        labels=parsed.point_labels,
        rate_hz=float(parsed.header.point_rate_hz),
        xyz=parsed.points.as_xyz().astype(np.float64),
        residuals=parsed.points.residual.astype(np.float64),
    )
