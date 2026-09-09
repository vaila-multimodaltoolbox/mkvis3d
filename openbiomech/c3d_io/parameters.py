"""C3D parameter-section parser (group/parameter records).

Record layout and the signed-byte conventions follow BTK's parameter loop in
`vendor/BTKCore/Code/IO/btkC3DFileIO.cpp` (`while (1) { nbCharLabel = ... }`):

* `nb_char_label` (int8) — length of the name; a *negative* value means the
  entry is locked. Zero terminates the section.
* `id` (int8) — non-zero. Negative identifies a **group**, positive a
  **parameter** belonging to the group with the matching magnitude.
* `offset` (uint16) — bytes from the start of the offset field itself to the
  next record, so the payload is `offset - 2` bytes. Zero marks the last
  entry.
* Parameters additionally carry `type` (int8: -1 char, 1 byte, 2 int16,
  4 float), a dimension count, the dimensions, the packed data, and a
  description.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .binary_stream import ByteOrder, C3DParseError

TYPE_CHAR = -1
TYPE_BYTE = 1
TYPE_INT16 = 2
TYPE_FLOAT = 4

_TYPE_NAMES = {TYPE_CHAR: "char", TYPE_BYTE: "byte", TYPE_INT16: "int16", TYPE_FLOAT: "float"}


@dataclass
class Parameter:
    """One parameter record, decoded into Python/numpy values."""

    name: str
    group_id: int
    data_type: int
    dimensions: tuple[int, ...]
    value: Any
    description: str = ""
    locked: bool = False

    @property
    def type_name(self) -> str:
        return _TYPE_NAMES.get(self.data_type, f"unknown({self.data_type})")


@dataclass
class Group:
    """One group record and the parameters that reference its id."""

    name: str
    group_id: int
    description: str = ""
    locked: bool = False
    parameters: dict[str, Parameter] = field(default_factory=dict)

    def get(self, parameter: str) -> Parameter | None:
        return self.parameters.get(parameter.upper())


def _read_i8(buf: bytes, pos: int) -> int:
    return int.from_bytes(buf[pos : pos + 1], "little", signed=True)


def _decode_string(raw: bytes) -> str:
    """C3D strings are fixed-width, space-padded, latin-1 in practice."""
    return raw.decode("latin-1").strip()


def _read_parameter_data(
    buf: bytes, pos: int, order: ByteOrder, data_type: int, dims: tuple[int, ...]
) -> tuple[Any, int]:
    """Decode `prod(dims)` elements of `data_type`; return (value, bytes_read)."""
    count = 1
    for d in dims:
        count *= int(d)

    if data_type == TYPE_CHAR:
        raw = buf[pos : pos + count]
        if len(dims) >= 2:
            width = int(dims[0])
            rows = count // width if width else 0
            value: Any = [_decode_string(raw[i * width : (i + 1) * width]) for i in range(rows)]
        else:
            value = [_decode_string(raw)]
        return value, count

    if data_type == TYPE_BYTE:
        value = np.frombuffer(buf, dtype="i1", count=count, offset=pos).astype(np.int64)
        if len(dims) > 1 and count > 0:
            value = value.reshape(dims, order="F")
        return value, count
    if data_type == TYPE_INT16:
        value = order.i16_array(buf, pos, count).astype(np.int64)
        if len(dims) > 1 and count > 0:
            value = value.reshape(dims, order="F")
        return value, count * 2
    if data_type == TYPE_FLOAT:
        value = order.f32_array(buf, pos, count).astype(np.float64)
        if len(dims) > 1 and count > 0:
            value = value.reshape(dims, order="F")
        return value, count * 4

    raise C3DParseError(f"Unknown parameter data type {data_type}")


def parse_parameters(buf: bytes, parameter_first_block: int, order: ByteOrder) -> dict[str, Group]:
    """Parse the whole parameter section into `{GROUP_NAME: Group}`.

    Group and parameter names are upper-cased so lookups are case-insensitive
    (`POINT:LABELS` is written in either case by different vendors).
    """
    section_start = 512 * (parameter_first_block - 1)
    if section_start + 4 > len(buf):
        raise C3DParseError("File truncated before the parameter section")

    # Bytes 1-2 are only meaningful when the section is also the file start;
    # byte 3 is the section's block count and byte 4 the processor flag.
    n_blocks = buf[section_start + 2]
    pos = section_start + 4
    section_end = min(len(buf), section_start + max(n_blocks, 1) * 512)

    groups: dict[int, Group] = {}
    pending: list[Parameter] = []

    while pos + 2 <= len(buf):
        nb_char_label = _read_i8(buf, pos)
        pos += 1
        if nb_char_label == 0:
            break  # end of the parameter section

        group_id = _read_i8(buf, pos)
        pos += 1
        if group_id == 0:
            raise C3DParseError("Parameter/group record with id 0")

        name_len = abs(nb_char_label)
        name = _decode_string(buf[pos : pos + name_len]).upper()
        pos += name_len

        offset_field_pos = pos
        offset = order.u16(buf, pos)
        pos += 2
        last_entry = offset == 0
        # `offset` is measured from the start of the offset field itself.
        next_record = offset_field_pos + offset
        locked = nb_char_label < 0

        if group_id < 0:
            desc_len = buf[pos]
            pos += 1
            description = _decode_string(buf[pos : pos + desc_len])
            pos += desc_len
            groups[-group_id] = Group(
                name=name, group_id=-group_id, description=description, locked=locked
            )
        else:
            data_type = _read_i8(buf, pos)
            pos += 1
            n_dims = _read_i8(buf, pos)
            pos += 1
            dims = tuple(int(b) for b in buf[pos : pos + max(n_dims, 0)])
            pos += max(n_dims, 0)

            value, data_bytes = _read_parameter_data(buf, pos, order, data_type, dims)
            pos += data_bytes

            description = ""
            if not last_entry and pos < next_record:
                desc_len = buf[pos]
                pos += 1
                description = _decode_string(buf[pos : pos + desc_len])
                pos += desc_len

            pending.append(
                Parameter(
                    name=name,
                    group_id=group_id,
                    data_type=data_type,
                    dimensions=dims,
                    value=value,
                    description=description,
                    locked=locked,
                )
            )

        if last_entry:
            break
        if next_record <= offset_field_pos or next_record > section_end:
            # A record pointing outside its own section means the file is
            # malformed or uses a vendor extension we do not follow; stop
            # rather than walking into the data section (BTK warns and bails
            # here too).
            break
        pos = next_record

    by_name: dict[str, Group] = {}
    for group in groups.values():
        by_name[group.name] = group
    for parameter in pending:
        group = groups.get(parameter.group_id)
        if group is None:
            continue  # orphan parameter: no matching group record
        group.parameters[parameter.name] = parameter
    return by_name
