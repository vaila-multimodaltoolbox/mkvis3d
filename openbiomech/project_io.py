"""Open, versioned ``.vaila`` project archives.

A project is a regular ZIP file containing UTF-8 JSON plus an optional copy
of the source motion file. It deliberately uses no pickle, executable code,
encrypted member, or proprietary codec.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

FORMAT_NAME = "vaila-project"
SCHEMA_VERSION = 1
MEDIA_TYPE = "application/vnd.vaila.project+zip"
MAX_MEMBERS = 32
MAX_UNCOMPRESSED_BYTES = 1 << 30


@dataclass(frozen=True)
class VailaProject:
    """Decoded project content."""

    trial: dict[str, Any]
    viewer_state: dict[str, Any]
    analyses: dict[str, Any]
    source_name: str | None = None
    source_bytes: bytes | None = None


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def _safe_source_name(name: str) -> str:
    basename = Path(name).name
    suffix = Path(basename).suffix.lower()
    if not basename or suffix not in (".c3d", ".csv", ".3d"):
        raise ValueError("project source must be a named .c3d, .csv, or .3d file")
    return basename


def vaila_project_bytes(
    trial: dict[str, Any],
    viewer_state: dict[str, Any],
    analyses: dict[str, Any],
    *,
    source_name: str | None = None,
    source_bytes: bytes | None = None,
) -> bytes:
    """Serialize complete application state to an open ``.vaila`` archive."""
    if not isinstance(trial, dict) or not isinstance(viewer_state, dict):
        raise ValueError("trial and viewer_state must be JSON objects")
    if not isinstance(analyses, dict):
        raise ValueError("analyses must be a JSON object")
    if (source_name is None) != (source_bytes is None):
        raise ValueError("source_name and source_bytes must be supplied together")

    members = {
        "trial.json": _json_bytes(trial),
        "viewer-state.json": _json_bytes(viewer_state),
        "analyses.json": _json_bytes(analyses),
    }
    source_member = None
    if source_name is not None and source_bytes is not None:
        safe_name = _safe_source_name(source_name)
        source_member = f"source/{safe_name}"
        members[source_member] = bytes(source_bytes)

    manifest: dict[str, Any] = {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION,
        "media_type": MEDIA_TYPE,
        "generator": "OpenBiomech (mkvis3d)",
        "members": {
            name: {
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in members.items()
        },
    }
    if source_member:
        manifest["source"] = source_member

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for name, content in members.items():
            archive.writestr(name, content)
    return stream.getvalue()


def _read_json_member(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        value = json.loads(archive.read(name))
    except KeyError as exc:
        raise ValueError(f"project is missing {name}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"project member {name} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"project member {name} must contain a JSON object")
    return value


def read_vaila_project(source: str | Path | bytes) -> VailaProject:
    """Read and integrity-check a ``.vaila`` archive."""
    raw = source if isinstance(source, bytes) else Path(source).read_bytes()
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid .vaila ZIP archive") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("project contains too many members")
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("project uncompressed size exceeds 1 GiB")
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or info.flag_bits & 0x1:
                raise ValueError("project contains an unsafe or encrypted member")

        manifest = _read_json_member(archive, "manifest.json")
        if (
            manifest.get("format") != FORMAT_NAME
            or manifest.get("schema_version") != SCHEMA_VERSION
        ):
            raise ValueError("unsupported .vaila format or schema version")
        declared = manifest.get("members")
        if not isinstance(declared, dict):
            raise ValueError("project manifest members must be an object")
        for name, metadata in declared.items():
            if not isinstance(name, str) or not isinstance(metadata, dict):
                raise ValueError("invalid project manifest member entry")
            try:
                content = archive.read(name)
            except KeyError as exc:
                raise ValueError(f"project is missing declared member {name}") from exc
            if len(content) != metadata.get("bytes"):
                raise ValueError(f"project member size mismatch: {name}")
            if hashlib.sha256(content).hexdigest() != metadata.get("sha256"):
                raise ValueError(f"project member checksum mismatch: {name}")

        trial = _read_json_member(archive, "trial.json")
        viewer_state = _read_json_member(archive, "viewer-state.json")
        analyses = _read_json_member(archive, "analyses.json")
        source_member = manifest.get("source")
        source_name = Path(source_member).name if isinstance(source_member, str) else None
        source_bytes = archive.read(source_member) if isinstance(source_member, str) else None
        return VailaProject(trial, viewer_state, analyses, source_name, source_bytes)
