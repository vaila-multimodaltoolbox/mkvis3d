"""Processor-aware binary primitives for the native C3D reader.

Implements the three C3D processor architectures documented in README.md §4.2
and dispatched by BTK's `Code/IO/btkC3DFileIO.cpp` (`IEEELittleEndian` /
`VAXLittleEndian` / `IEEEBigEndian` stream classes):

* 84 (0x54) — Intel, little-endian, IEEE-754 floats.
* 85 (0x55) — DEC VAX, little-endian integers, VAX F-float reals.
* 86 (0x56) — MIPS/SGI, big-endian, IEEE-754 floats.

The VAX path is reconstructed arithmetically (no hardware emulation): VAX
F-float normalises its mantissa to [0.5, 1) with a hidden leading bit and an
excess-128 exponent, whereas IEEE-754 binary32 normalises to [1, 2) with
excess-127, so the mantissa bits transfer unchanged and only the exponent
shifts by 2. The two 16-bit halves are also stored in the opposite order to
the IEEE layout, hence the word swap.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

INTEL = 84
DEC_VAX = 85
MIPS = 86

PROCESSOR_NAMES = {INTEL: "Intel (IEEE LE)", DEC_VAX: "DEC VAX (VAX LE)", MIPS: "MIPS (IEEE BE)"}


class C3DParseError(ValueError):
    """Raised when a file does not conform to the C3D layout we can decode."""


def vax_f_to_float32(vax_bits: np.ndarray) -> np.ndarray:
    """Convert VAX F-float bit patterns (as uint32, file byte order) to float32.

    Vectorised port of the reference snippet in README.md §4.2. `vax_bits` is
    the raw 4 bytes read as a *little-endian* uint32, so its low half is the
    first 16-bit word in the file.

    A zero or reserved exponent (VAX "dirty zero" / reserved operand) decodes
    to 0.0 rather than raising, matching how readers in the wild treat legacy
    files; VAX has no Inf/NaN encodings to preserve.
    """
    bits = np.asarray(vax_bits, dtype=np.uint32)
    word0 = (bits & 0xFFFF).astype(np.uint32)  # first word in the file
    word1 = ((bits >> 16) & 0xFFFF).astype(np.uint32)  # second word in the file

    sign = (word0 >> 15) & 0x1
    exponent = (word0 >> 7) & 0xFF
    fraction = ((word0 & 0x7F) << 16) | word1

    # IEEE exponent = VAX exponent - 128 + 127 - 1 (see module docstring).
    ieee_exponent = (exponent.astype(np.int64) - 2).astype(np.int64)
    ieee_bits = (
        (sign.astype(np.uint32) << 31) | ((ieee_exponent & 0xFF).astype(np.uint32) << 23) | fraction
    )
    out = (
        ieee_bits.view(np.float32) if ieee_bits.dtype == np.uint32 else ieee_bits.astype(np.float32)
    )
    out = np.asarray(out, dtype=np.float32).copy()
    out[exponent == 0] = np.float32(0.0)
    return out


@dataclass(frozen=True)
class ByteOrder:
    """Struct/numpy dtype selection for one C3D processor architecture."""

    processor: int

    @property
    def name(self) -> str:
        return PROCESSOR_NAMES.get(self.processor, f"unknown ({self.processor})")

    @property
    def int_prefix(self) -> str:
        """Endianness prefix for integer fields ('<' or '>')."""
        return ">" if self.processor == MIPS else "<"

    @property
    def is_vax_float(self) -> bool:
        return self.processor == DEC_VAX

    def u16(self, buf: bytes, offset: int) -> int:
        return int(np.frombuffer(buf, dtype=f"{self.int_prefix}u2", count=1, offset=offset)[0])

    def i16(self, buf: bytes, offset: int) -> int:
        return int(np.frombuffer(buf, dtype=f"{self.int_prefix}i2", count=1, offset=offset)[0])

    def u16_array(self, buf: bytes, offset: int, count: int) -> np.ndarray:
        return np.frombuffer(buf, dtype=f"{self.int_prefix}u2", count=count, offset=offset)

    def i16_array(self, buf: bytes, offset: int, count: int) -> np.ndarray:
        return np.frombuffer(buf, dtype=f"{self.int_prefix}i2", count=count, offset=offset)

    def f32(self, buf: bytes, offset: int) -> float:
        return float(self.f32_array(buf, offset, 1)[0])

    def f32_array(self, buf: bytes, offset: int, count: int) -> np.ndarray:
        """Read `count` 32-bit reals, decoding VAX F-float when applicable."""
        if self.is_vax_float:
            bits = np.frombuffer(buf, dtype="<u4", count=count, offset=offset)
            return vax_f_to_float32(bits)
        return np.frombuffer(buf, dtype=f"{self.int_prefix}f4", count=count, offset=offset)


def detect_byte_order(buf: bytes, parameter_first_block: int) -> ByteOrder:
    """Read the processor flag at byte 4 of the parameter section.

    BTK accepts both the canonical 84/85/86 values and the bare 1/2/3 written
    by some buggy exporters (`btkC3DFileIO.cpp`, the fall-through `case`
    labels); we accept the same range and normalise to 84/85/86.
    """
    position = 512 * (parameter_first_block - 1) + 3
    if position >= len(buf):
        raise C3DParseError("File truncated before the parameter section header")
    raw = buf[position]
    processor = raw + 83 if raw in (1, 2, 3) else raw
    if processor not in PROCESSOR_NAMES:
        raise C3DParseError(f"Invalid processor type {raw} (expected 84, 85 or 86)")
    return ByteOrder(processor=processor)
