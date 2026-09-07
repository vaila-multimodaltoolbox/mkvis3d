"""C3D header block (block 1) decoding — README.md §4.1.

Field layout and validation follow BTK's `C3DFileIO::Read`
(`vendor/BTKCore/Code/IO/btkC3DFileIO.cpp`, the `// Header` section).
"""

from __future__ import annotations

from dataclasses import dataclass

from .binary_stream import ByteOrder, C3DParseError, detect_byte_order

HEADER_KEY = 80  # 0x50
BLOCK_SIZE = 512


@dataclass(frozen=True)
class C3DHeader:
    """Decoded header block.

    Attributes:
        parameter_first_block: 1-based block index of the parameter section.
        processor: 84 (Intel), 85 (DEC VAX) or 86 (MIPS).
        n_points: 3D points stored per frame (header word 2).
        analog_samples_per_frame: total analog measurements per 3D frame
            (word 3) = n_analog_channels * analog_subsamples.
        first_frame / last_frame: 1-based inclusive frame range (words 4-5).
        max_interpolation_gap: word 6.
        point_scale: word 7-8. Negative means points are stored as 32-bit
            floats; positive means 16-bit signed integers scaled by its
            magnitude.
        data_first_block: 1-based block index of the 3D/analog data (word 9).
        analog_subsamples: analog samples per video frame (word 10).
        point_rate_hz: video/point sampling frequency (words 11-12).
    """

    parameter_first_block: int
    processor: int
    n_points: int
    analog_samples_per_frame: int
    first_frame: int
    last_frame: int
    max_interpolation_gap: int
    point_scale: float
    data_first_block: int
    analog_subsamples: int
    point_rate_hz: float

    @property
    def n_frames(self) -> int:
        return self.last_frame - self.first_frame + 1

    @property
    def is_float_format(self) -> bool:
        """True when 3D/analog values are stored as 32-bit reals."""
        return self.point_scale < 0.0

    @property
    def n_analog_channels(self) -> int:
        if self.analog_subsamples <= 0:
            return 0
        return self.analog_samples_per_frame // self.analog_subsamples


def parse_header(buf: bytes) -> tuple[C3DHeader, ByteOrder]:
    """Decode block 1 and the processor flag it points at."""
    if len(buf) < BLOCK_SIZE:
        raise C3DParseError(f"File shorter than one 512-byte block ({len(buf)} bytes)")

    parameter_first_block = int.from_bytes(buf[0:1], "little", signed=True)
    if parameter_first_block <= 0:
        raise C3DParseError(f"Bad parameter first block number: {parameter_first_block}")
    if buf[1] != HEADER_KEY:
        raise C3DParseError(f"Bad header key: {buf[1]} (expected {HEADER_KEY})")

    order = detect_byte_order(buf, parameter_first_block)

    n_points = order.u16(buf, 2)
    analog_samples_per_frame = order.u16(buf, 4)
    first_frame = order.u16(buf, 6)
    last_frame = order.u16(buf, 8)
    max_interpolation_gap = order.u16(buf, 10)
    point_scale = order.f32(buf, 12)
    if point_scale == 0.0:
        raise C3DParseError("Incorrect 3D scale factor (0.0)")
    data_first_block = order.u16(buf, 16)
    if data_first_block < 2:
        raise C3DParseError(f"Bad data first block: {data_first_block}")
    analog_subsamples = order.u16(buf, 18)
    point_rate_hz = order.f32(buf, 20)

    if analog_samples_per_frame and analog_subsamples <= 0:
        raise C3DParseError("Analog samples present but the samples-per-frame ratio (word 10) is 0")

    return (
        C3DHeader(
            parameter_first_block=parameter_first_block,
            processor=order.processor,
            n_points=n_points,
            analog_samples_per_frame=analog_samples_per_frame,
            first_frame=first_frame,
            last_frame=last_frame,
            max_interpolation_gap=max_interpolation_gap,
            point_scale=point_scale,
            data_first_block=data_first_block,
            analog_subsamples=analog_subsamples,
            point_rate_hz=point_rate_hz,
        ),
        order,
    )
