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

from ..marker_trial import ForcePlatform, MarkerTrial
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


def extract_force_platforms(
    parsed: C3DFile, point_factor: float, *, f_threshold: float = 15.0
) -> list[ForcePlatform]:
    """Extract and calibrate physical force platforms from a parsed C3D file.

    Follows the BTK / Visual3D / Shimba (1984) formulation for Type-2 (AMTI / Bertec)
    6-component force plates, transforming Center of Pressure (COP) and Ground
    Reaction Force (GRF) into the global laboratory frame.
    """
    if "FORCE_PLATFORM" not in parsed.groups or not parsed.analog or parsed.analog.n_channels == 0:
        return []

    fp_grp = parsed.groups["FORCE_PLATFORM"]
    used_val = fp_grp.get("USED")
    if used_val is None:
        return []
    n_used = int(np.atleast_1d(used_val.value)[0])
    if n_used <= 0:
        return []

    corners_val = fp_grp.get("CORNERS")
    origin_val = fp_grp.get("ORIGIN")
    channel_val = fp_grp.get("CHANNEL")
    type_val = fp_grp.get("TYPE")
    if corners_val is None or channel_val is None or type_val is None:
        return []

    corners = np.asarray(corners_val.value, dtype=np.float64) * point_factor
    if corners.ndim == 2:
        corners = corners[:, :, np.newaxis]
    elif corners.ndim == 1:
        corners = corners.reshape((3, 4, -1), order="F")

    origin = (
        np.asarray(origin_val.value if origin_val is not None else 0.0, dtype=np.float64)
        * point_factor
    )
    if origin.ndim == 1 and origin.size == 3 * corners.shape[2]:
        origin = origin.reshape((3, -1), order="F")
    elif origin.ndim == 1:
        origin = origin[:, np.newaxis]

    channel = np.asarray(channel_val.value, dtype=np.int64)
    if channel.ndim == 1:
        channel = channel.reshape((-1, corners.shape[2]), order="F")

    types = np.atleast_1d(np.asarray(type_val.value, dtype=np.int64))

    analog_units = _group_values(parsed.groups, "ANALOG", "UNITS")
    analog_vals = parsed.analog.values
    n_frames = parsed.points.n_frames
    if analog_vals.ndim == 3 and analog_vals.shape[1] > 0:
        analog_by_frame = analog_vals.mean(axis=1)
    else:
        analog_by_frame = analog_vals.reshape(n_frames, -1)

    platforms: list[ForcePlatform] = []
    for p in range(min(n_used, corners.shape[2])):
        c = corners[:, :, p]
        diag = np.linalg.norm(c[:, 0] - c[:, 2])
        # Filter out degenerate/dummy plates (e.g. tiny 0.02m placeholders in some lab setups)
        if (
            diag < 0.05
            or np.linalg.norm(c[:, 0] - c[:, 1]) < 1e-6
            or np.linalg.norm(c[:, 0] - c[:, 3]) < 1e-6
        ):
            continue

        ptype = int(types[p]) if p < len(types) else 2
        ch_raw = channel[:, p] if p < channel.shape[1] else []
        ch_indices = [int(x) - 1 for x in ch_raw if int(x) > 0]
        if len(ch_indices) < 6 or max(ch_indices) >= parsed.analog.n_channels:
            continue

        # Detect moment units: C3D often stores moments in N*mm
        m_scale = 1.0
        if analog_units is not None and len(analog_units) > ch_indices[3]:
            unit_str = str(analog_units[ch_indices[3]]).strip().upper()
            if "MM" in unit_str:
                m_scale = 0.001
            elif "CM" in unit_str:
                m_scale = 0.01

        f_local = analog_by_frame[:, ch_indices[:3]]
        m_local = analog_by_frame[:, ch_indices[3:6]] * m_scale
        orig = origin[:, p] if p < origin.shape[1] else np.zeros(3)

        x0, y0, z0 = orig[0], orig[1], orig[2]
        fx, fy, fz = f_local[:, 0], f_local[:, 1], f_local[:, 2]
        mx, my, mz = m_local[:, 0], m_local[:, 1], m_local[:, 2]

        # Origin offset moment correction (README §3.5.2 / BTK)
        mx_s = mx + fy * z0 - fz * y0
        my_s = my - fx * z0 + fz * x0
        mz_s = mz + fx * y0 - fy * x0

        sNF = fx**2 + fy**2 + fz**2
        contact = np.abs(fz) >= f_threshold
        denom = sNF * fz
        safe = contact & (np.abs(denom) > 1e-9) & (sNF > 1e-9)

        with np.errstate(divide="ignore", invalid="ignore"):
            px = np.where(
                safe,
                (fy * mz_s - fz * my_s) / sNF - (fx**2 * my_s - fx * (fy * mx_s)) / denom,
                0.0,
            )
            py = np.where(
                safe,
                (fz * mx_s - fx * mz_s) / sNF - (fx * (fy * my_s) - fy**2 * mx_s) / denom,
                0.0,
            )
            pz = np.zeros_like(px)

        p_local = np.stack([px, py, pz], axis=-1)

        # Plate orientation matrix R and surface center t from corners (m)
        col0 = c[:, 0] - c[:, 1]
        col0 = col0 / np.linalg.norm(col0)
        col2 = np.cross(col0, c[:, 0] - c[:, 3])
        col2 = col2 / np.linalg.norm(col2)
        col1 = np.cross(col2, col0)
        R = np.column_stack([col0, col1, col2])
        t = (c[:, 0] + c[:, 2]) / 2.0

        cop_global = p_local @ R.T + t
        cop_global[~contact] = np.nan

        # Ground Reaction Force (reaction upwards against gravity)
        grf_global = f_local @ R.T
        grf_global[~contact] = 0.0

        m_free_local = np.stack([mx_s, my_s, mz_s], axis=-1) - np.cross(p_local, f_local)
        moment_global = m_free_local @ R.T
        moment_global[~contact] = 0.0

        platforms.append(
            ForcePlatform(
                id=p,
                name=f"FP{len(platforms) + 1}",
                plate_type=ptype,
                corners=c.T,
                origin=orig,
                channels=tuple(ch_indices),
                cop=cop_global,
                force=grf_global,
                moment=moment_global,
                contact=contact,
            )
        )
    return platforms


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

    raw_units = _group_values(parsed.groups, "POINT", "UNITS")
    units = str(np.atleast_1d(raw_units)[0]).strip().lower() if raw_units is not None else ""
    factors = {"m": 1.0, "mm": 0.001, "cm": 0.01}
    if units not in factors:
        raise ValueError(f"unsupported or missing POINT:UNITS: {units!r}; expected m, cm, mm")
    factor = factors[units]

    force_plates = extract_force_platforms(parsed, factor)
    analog_labels = parsed.analog.labels if parsed.analog else ()
    analog_rate_hz = float(parsed.analog.rate_hz) if parsed.analog else 0.0

    return MarkerTrial(
        labels=parsed.point_labels,
        rate_hz=float(parsed.header.point_rate_hz),
        xyz=parsed.points.as_xyz().astype(np.float64) * factor,
        residuals=np.where(parsed.points.residual < 0, -1.0, parsed.points.residual * factor),
        force_plates=force_plates,
        analog_labels=analog_labels,
        analog_rate_hz=analog_rate_hz,
    )
