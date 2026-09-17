"""Offline HTML viewer and a loopback-only motion file interface.

Stdlib HTTP and native readers; no CDN or vailá runtime dependency.
"""

from __future__ import annotations

import contextlib
import json
import secrets
import sys
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

from .analysis_io import run_dynamics
from .biomech_math.lcs import transform_trial_monocular_to_standard
from .c3d_io import c3d_bytes
from .kinematic_analysis import (
    TAIT_BRYAN_SEQUENCES,
    add_virtual_points_to_trial,
    blank_marker_frames,
    build_orthonormal_basis,
    evaluate_virtual_point_expression,
    export_marker_trajectory_csv,
    load_marker_trajectory_csv,
    marker_frame_orientations,
    relative_segment_kinematics,
)
from .marker_trial import MarkerTrial
from .project_io import VailaProject, read_vaila_project, vaila_project_bytes
from .trial_io import load_trial
from .video_compat import (
    ensure_browser_video,
    ffmpeg_suggestion,
    pick_local_video_path,
)


def get_project_root() -> Path:
    """Return project root directory, accommodating PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def load_all_skeleton_templates() -> dict[str, dict]:
    """Load all JSON skeleton templates found in skeleton_templates/."""
    templates_dir = get_project_root() / "skeleton_templates"
    templates = {}
    if templates_dir.is_dir():
        for f in sorted(templates_dir.glob("*.json")):
            with contextlib.suppress(Exception):
                templates[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return templates


def trial_payload(trial: MarkerTrial, name: str) -> dict:
    if not np.isfinite(trial.rate_hz) or trial.rate_hz <= 0:
        raise ValueError("trial rate must be finite and positive")
    xyz = np.asarray(trial.xyz, dtype=np.float64)
    if xyz.ndim != 3 or xyz.shape[2] != 3 or not xyz.shape[0] or xyz.shape[1] != len(trial.labels):
        raise ValueError("trial must contain frames and matching marker labels")
    if not np.isfinite(xyz).all(axis=-1).any():
        raise ValueError("trial has no visible marker samples")
    safe = xyz.astype(object)
    safe[~np.isfinite(xyz)] = None

    force_plates_data = []
    for fp in getattr(trial, "force_plates", []):
        cop_safe = fp.cop.astype(object)
        cop_safe[~np.isfinite(fp.cop)] = None
        force_safe = fp.force.astype(object)
        force_safe[~np.isfinite(fp.force)] = 0.0
        force_plates_data.append(
            {
                "id": fp.id,
                "name": fp.name,
                "type": fp.plate_type,
                "corners": fp.corners.tolist(),
                "origin": fp.origin.tolist(),
                "cop": cop_safe.tolist(),
                "force": force_safe.tolist(),
                "contact": fp.contact.tolist(),
            }
        )

    payload = {
        "name": name,
        "labels": list(trial.labels),
        "rate_hz": float(trial.rate_hz),
        "xyz": safe.tolist(),
    }
    if force_plates_data:
        payload["force_plates"] = force_plates_data
    if getattr(trial, "analog_labels", ()):
        payload["analog_labels"] = list(trial.analog_labels)
        payload["analog_units"] = list(trial.analog_units)
        payload["analog_rate_hz"] = float(trial.analog_rate_hz)
        analog = np.asarray(trial.analog, dtype=np.float64)
        analog_safe = analog.astype(object)
        analog_safe[~np.isfinite(analog)] = None
        payload["analog"] = analog_safe.tolist()
    return payload


def trial_from_payload(payload: dict) -> MarkerTrial:
    """Validate browser-edited point data and rebuild a marker trial."""
    labels = tuple(str(label) for label in payload.get("labels", ()))
    rate_hz = float(payload.get("rate_hz", 0.0))
    xyz = np.asarray(payload.get("xyz"), dtype=np.float64)
    if xyz.ndim != 3 or xyz.shape[1:] != (len(labels), 3):
        raise ValueError("edited trial xyz must match its marker labels")
    if not xyz.shape[0] or not labels:
        raise ValueError("edited trial must contain frames and markers")
    if not np.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError("edited trial rate must be finite and positive")
    visible = np.isfinite(xyz).all(axis=2)
    if not visible.any():
        raise ValueError("edited trial has no visible marker samples")
    residuals = np.where(visible, 0.0, np.nan)
    analog_labels = tuple(str(label) for label in payload.get("analog_labels", ()))
    analog_units = tuple(str(unit) for unit in payload.get("analog_units", ()))
    analog = np.asarray(payload.get("analog", []), dtype=np.float64)
    if analog_labels:
        if analog.ndim != 3 or analog.shape[0] != xyz.shape[0]:
            raise ValueError("edited trial analog data must align with point frames")
        if analog.shape[2] != len(analog_labels):
            raise ValueError("edited trial analog channels must match analog labels")
        if analog_units and len(analog_units) != len(analog_labels):
            raise ValueError("edited trial analog units must match analog labels")
    else:
        analog = np.zeros((xyz.shape[0], 0, 0), dtype=np.float64)
    analog_rate_hz = float(payload.get("analog_rate_hz", 0.0))
    if analog_labels:
        expected_analog_rate = rate_hz * analog.shape[1]
        if not np.isclose(analog_rate_hz, expected_analog_rate, rtol=1e-9, atol=1e-9):
            raise ValueError("edited trial analog rate must equal point rate times subsamples")
    return MarkerTrial(
        labels=labels,
        rate_hz=rate_hz,
        xyz=xyz,
        residuals=residuals,
        analog_labels=analog_labels,
        analog_units=analog_units,
        analog_rate_hz=analog_rate_hz,
        analog=analog,
    )


def json_compatible(value):
    """Convert NumPy analysis results to strict JSON-compatible values."""
    if isinstance(value, np.ndarray):
        if np.issubdtype(value.dtype, np.floating):
            safe = value.astype(object)
            safe[~np.isfinite(value)] = None
            return safe.tolist()
        return value.tolist()
    if isinstance(value, dict):
        return {key: json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def render_viewer(
    payload: dict | None = None,
    *,
    server: bool = False,
    skeleton_templates: dict[str, dict] | None = None,
    project: dict | None = None,
) -> str:
    from openbiomech import __version__

    directory = Path(__file__).parent
    if skeleton_templates is None:
        skeleton_templates = load_all_skeleton_templates()
    templates_json = json.dumps(skeleton_templates, ensure_ascii=True).replace("<", "\\u003c")
    data = json.dumps(
        {"server": server, "trial": payload, "project": project},
        ensure_ascii=True,
        allow_nan=False,
    )
    data = data.replace("<", "\\u003c")
    return (
        (directory / "viewer.html")
        .read_text(encoding="utf-8")
        .replace("__APP_VERSION__", __version__)
        .replace("__TRIAL_DATA__", data)
        .replace("__SKELETON_TEMPLATES__", templates_json)
        .replace("__VIEWER_SCRIPT__", (directory / "viewer.js").read_text(encoding="utf-8"))
    )


def export_viewer(trial: MarkerTrial, name: str, output: Path) -> None:
    html = render_viewer(trial_payload(trial, name))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def create_server(
    port: int = 0,
    initial_payload: dict | None = None,
    *,
    initial_source_name: str | None = None,
    initial_source_bytes: bytes | None = None,
    initial_project: dict | None = None,
    source_dir: Path | None = None,
    initial_videos: list[Path] | None = None,
) -> tuple[ThreadingHTTPServer, str]:
    """Bind loopback; uploads need a per-session token, never a disk path."""
    token = secrets.token_urlsafe(32)
    current_trial: list[dict | None] = [initial_payload]
    current_source: list[tuple[str, bytes] | None] = [
        (initial_source_name, initial_source_bytes)
        if initial_source_name is not None and initial_source_bytes is not None
        else None
    ]
    current_project: list[dict | None] = [initial_project]
    # name -> absolute path; grows when we register H.264 cache outputs / uploads
    video_registry: dict[str, Path] = {}
    upload_scratch: list[Path] = []  # session-lived dirs for uploaded video re-encodes
    if initial_videos:
        for v in initial_videos:
            if v.is_file():
                video_registry[v.name] = v.resolve()

    def resolve_video(video_name: str) -> Path | None:
        safe = Path(video_name).name
        if not safe:
            return None
        registered = video_registry.get(safe)
        if registered is not None and registered.is_file():
            return registered
        if source_dir and source_dir.is_dir():
            candidate = source_dir / safe
            if candidate.is_file():
                video_registry[safe] = candidate.resolve()
                return video_registry[safe]
        return None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            pass

        def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            req_path = parsed.path

            if req_path == "/favicon.ico":
                icon_path = get_project_root() / "assets" / "icons" / "vaila.ico"
                if not icon_path.is_file():
                    fallback = Path("/home/preto/data/vaila/docs/images/vaila_ico_trans.ico")
                    if fallback.is_file():
                        icon_path = fallback
                if icon_path.is_file():
                    self.send_bytes(200, icon_path.read_bytes(), "image/x-icon")
                    return
                self.send_bytes(404, b"Not found", "text/plain")
                return

            if req_path == "/api/examples":
                data_dir = get_project_root() / "data"
                examples = []
                if data_dir.exists():
                    for ext in (".c3d", ".csv", ".3d"):
                        for f in sorted(data_dir.glob(f"*{ext}")):
                            examples.append({"name": f.name, "size": f.stat().st_size})
                self.send_bytes(
                    200, json.dumps({"examples": examples}).encode(), "application/json"
                )
                return

            if req_path == "/api/example":
                query = parse_qs(parsed.query)
                name = Path(query.get("name", [""])[0]).name
                data_dir = get_project_root() / "data"
                target = data_dir / name
                if not target.is_file():
                    self.send_bytes(404, b'{"error":"Example not found"}', "application/json")
                    return
                try:
                    payload = trial_payload(load_trial(target), name)
                    current_trial[0] = payload
                    self.send_bytes(
                        200, json.dumps(payload, allow_nan=False).encode(), "application/json"
                    )
                except Exception as exc:
                    self.send_bytes(
                        400, json.dumps({"error": str(exc)}).encode(), "application/json"
                    )
                return

            if req_path == "/api/companion_videos":
                videos = []
                seen: set[str] = set()
                for name, path in list(video_registry.items()):
                    if path.is_file() and name not in seen:
                        videos.append({"name": name, "size": path.stat().st_size})
                        seen.add(name)
                if source_dir and source_dir.is_dir():
                    for ext in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"):
                        for f in sorted(source_dir.glob(f"*{ext}")):
                            if f.name not in seen:
                                video_registry[f.name] = f.resolve()
                                videos.append({"name": f.name, "size": f.stat().st_size})
                                seen.add(f.name)
                self.send_bytes(200, json.dumps({"videos": videos}).encode(), "application/json")
                return

            if req_path == "/api/ensure_browser_video":
                query = parse_qs(parsed.query)
                video_name = Path(query.get("name", [""])[0]).name
                target_video = resolve_video(video_name)
                if not target_video:
                    self.send_bytes(404, b'{"error":"Video not found"}', "application/json")
                    return
                try:
                    playable, info = ensure_browser_video(target_video)
                    video_registry[playable.name] = playable.resolve()
                    # Keep original name mapped to playable so /api/video?name=original works.
                    video_registry[video_name] = playable.resolve()
                    body = {
                        "name": playable.name,
                        "original_name": video_name,
                        "path": str(playable),
                        "url": f"/api/video?name={playable.name}",
                        "transcoded": bool(info.get("transcoded")),
                        "codec_name": info.get("codec_name"),
                        "codec_tag_string": info.get("codec_tag_string"),
                        "suggestion": ffmpeg_suggestion(video_name),
                    }
                    self.send_bytes(
                        200, json.dumps(body, allow_nan=False).encode(), "application/json"
                    )
                except Exception as exc:
                    self.send_bytes(
                        400,
                        json.dumps(
                            {
                                "error": str(exc),
                                "suggestion": ffmpeg_suggestion(video_name),
                            }
                        ).encode(),
                        "application/json",
                    )
                return

            if req_path == "/api/video":
                query = parse_qs(parsed.query)
                video_name = Path(query.get("name", [""])[0]).name
                target_video = resolve_video(video_name)

                if not target_video or not target_video.is_file():
                    self.send_bytes(404, b'{"error":"Video not found"}', "application/json")
                    return

                file_size = target_video.stat().st_size
                ext = target_video.suffix.lower()
                mime = (
                    "video/mp4"
                    if ext in (".mp4", ".m4v")
                    else "video/webm"
                    if ext == ".webm"
                    else "video/quicktime"
                    if ext == ".mov"
                    else "video/x-matroska"
                    if ext == ".mkv"
                    else "video/octet-stream"
                )

                range_header = self.headers.get("Range")
                if range_header and range_header.startswith("bytes="):
                    try:
                        byte_range = range_header.split("=")[1].strip()
                        parts = byte_range.split("-")
                        start = int(parts[0]) if parts[0] else 0
                        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
                        end = min(end, file_size - 1)
                        if start > end or start >= file_size:
                            self.send_response(416)
                            self.send_header("Content-Range", f"bytes */{file_size}")
                            self.end_headers()
                            return
                        length = end - start + 1
                        self.send_response(206)
                        self.send_header("Content-Type", mime)
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                        self.send_header("Content-Length", str(length))
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Cache-Control", "public, max-age=3600")
                        self.end_headers()
                        with open(target_video, "rb") as vf:
                            vf.seek(start)
                            chunk_size = 64 * 1024
                            remaining = length
                            while remaining > 0:
                                chunk = vf.read(min(chunk_size, remaining))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                        return
                    except (ConnectionResetError, BrokenPipeError):
                        return

                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                try:
                    with open(target_video, "rb") as vf:
                        chunk_size = 64 * 1024
                        while True:
                            chunk = vf.read(chunk_size)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                except (ConnectionResetError, BrokenPipeError):
                    pass
                return

            if req_path == "/api/current_trial":
                if current_trial[0] is not None:
                    self.send_bytes(
                        200,
                        json.dumps(current_trial[0], allow_nan=False).encode(),
                        "application/json",
                    )
                else:
                    self.send_bytes(200, b"null", "application/json")
                return

            if req_path == "/api/skeleton_templates":
                templates = load_all_skeleton_templates()
                summary = []
                for k, v in templates.items():
                    kps = v.get("keypoints", [])
                    conns = v.get("connections", [])
                    summary.append(
                        {
                            "id": k,
                            "schema": v.get("schema", k),
                            "num_keypoints": v.get("num_keypoints", len(kps)),
                            "num_connections": len(conns),
                            "note": v.get("note", ""),
                        }
                    )
                self.send_bytes(
                    200, json.dumps({"templates": summary}).encode(), "application/json"
                )
                return

            if req_path == "/api/skeleton_template":
                query = parse_qs(parsed.query)
                name = Path(query.get("name", [""])[0]).stem
                templates = load_all_skeleton_templates()
                if name in templates:
                    self.send_bytes(200, json.dumps(templates[name]).encode(), "application/json")
                else:
                    self.send_bytes(404, b'{"error":"Template not found"}', "application/json")
                return

            if req_path != "/":
                self.send_bytes(404, b"Not found", "text/plain")
                return

            active_payload = current_trial[0] if current_trial[0] is not None else initial_payload
            self.send_bytes(
                200,
                render_viewer(
                    payload=active_payload,
                    server=True,
                    project=current_project[0],
                ).encode(),
                "text/html; charset=utf-8",
            )

        def do_POST(self) -> None:
            req_path = urlsplit(self.path).path
            if req_path not in (
                "/api/trial",
                "/api/export/c3d",
                "/api/export/vaila",
                "/api/analyze/orientation",
                "/api/analyze/kinematics_bases",
                "/api/analyze/evaluate_point",
                "/api/analyze/import_trajectory_csv",
                "/api/analyze/export_trajectory_csv",
                "/api/analyze/blank_frames",
                "/api/analyze/convert_monocular",
                "/api/analyze/dynamics",
                "/api/transcode_upload",
                "/api/pick_and_ensure_video",
                "/api/shutdown",
            ):
                self.send_bytes(404, b"Not found", "text/plain")
                return
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_bytes(403, b'{"error":"Session token required"}', "application/json")
                return
            if req_path == "/api/shutdown":
                self.send_bytes(200, b'{"status":"shutting down"}', "application/json")
                self.server.shutdown()
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if req_path == "/api/pick_and_ensure_video":
                    # Native dialog on the host — no body required.
                    if length > 0:
                        self.rfile.read(length)
                    chosen = pick_local_video_path()
                    if chosen is None:
                        self.send_bytes(
                            400,
                            json.dumps(
                                {
                                    "error": "No video selected (or zenity/kdialog unavailable)",
                                    "suggestion": ffmpeg_suggestion("input.mp4"),
                                }
                            ).encode(),
                            "application/json",
                        )
                        return
                    playable, info = ensure_browser_video(chosen)
                    video_registry[chosen.name] = chosen.resolve()
                    video_registry[playable.name] = playable.resolve()
                    # Remap original name to playable so subsequent /api/video hits H.264.
                    video_registry[chosen.name] = playable.resolve()
                    body = {
                        "name": playable.name,
                        "original_name": chosen.name,
                        "path": str(playable),
                        "url": f"/api/video?name={playable.name}",
                        "transcoded": bool(info.get("transcoded")),
                        "codec_name": info.get("codec_name"),
                        "codec_tag_string": info.get("codec_tag_string"),
                        "suggestion": ffmpeg_suggestion(chosen.name),
                    }
                    self.send_bytes(
                        200, json.dumps(body, allow_nan=False).encode(), "application/json"
                    )
                    return
                if not 0 < length <= 256 * 1024 * 1024:
                    raise ValueError("file must be nonempty and no larger than 256 MiB")
                if req_path == "/api/transcode_upload":
                    query = parse_qs(urlsplit(self.path).query)
                    original_name = Path(query.get("name", ["upload.mp4"])[0]).name or "upload.mp4"
                    # Optional absolute path on the host (loopback GUI) so we can
                    # write *_compress.mp4 beside the real file.
                    local_path_raw = (query.get("local_path", [""])[0] or "").strip()
                    local_source: Path | None = None
                    if local_path_raw:
                        candidate = Path(local_path_raw).expanduser()
                        if candidate.is_file() and candidate.name == original_name:
                            local_source = candidate.resolve()
                    suffix = Path(original_name).suffix.lower() or ".mp4"
                    if suffix not in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"):
                        raise ValueError("expected a video file (.mp4/.mov/.mkv/.webm/.avi/.m4v)")
                    uploaded = self.rfile.read(length)
                    if local_source is not None:
                        playable, info = ensure_browser_video(local_source)
                        video_registry[local_source.name] = playable.resolve()
                    else:
                        scratch = Path(tempfile.mkdtemp(prefix="openbiomech-video-"))
                        upload_scratch.append(scratch)
                        source = scratch / original_name
                        source.write_bytes(uploaded)
                        # Browser file inputs have no filesystem path — compress in
                        # scratch and serve via /api/video. Use Load Video (host
                        # dialog) to write *_compress.mp4 beside the original.
                        playable, info = ensure_browser_video(source)
                    video_registry[playable.name] = playable.resolve()
                    video_registry[original_name] = playable.resolve()
                    body = {
                        "name": playable.name,
                        "original_name": original_name,
                        "path": str(playable),
                        "url": f"/api/video?name={playable.name}",
                        "transcoded": bool(info.get("transcoded")),
                        "codec_name": info.get("codec_name"),
                        "codec_tag_string": info.get("codec_tag_string"),
                        "suggestion": ffmpeg_suggestion(original_name),
                    }
                    self.send_bytes(
                        200, json.dumps(body, allow_nan=False).encode(), "application/json"
                    )
                    return
                if req_path == "/api/export/c3d":
                    payload = json.loads(self.rfile.read(length))
                    if isinstance(payload, dict) and "trial" in payload:
                        trial_data = payload["trial"]
                        custom_filename = payload.get("filename") or payload.get("save_as_path")
                    else:
                        trial_data = payload
                        custom_filename = None
                    template = (
                        current_source[0][1]
                        if current_source[0] and Path(current_source[0][0]).suffix.lower() == ".c3d"
                        else None
                    )
                    body = c3d_bytes(trial_from_payload(trial_data), template=template)
                    if custom_filename and source_dir and source_dir.is_dir():
                        target_name = Path(str(custom_filename)).name
                        if not target_name.lower().endswith(".c3d"):
                            target_name += ".c3d"
                        with contextlib.suppress(OSError):
                            (source_dir / target_name).write_bytes(body)
                    self.send_bytes(200, body, "application/octet-stream")
                    return
                if req_path == "/api/export/vaila":
                    project = json.loads(self.rfile.read(length))
                    edited = project["trial"]
                    trial_from_payload(edited)
                    source_name = current_source[0][0] if current_source[0] else None
                    source_bytes = current_source[0][1] if current_source[0] else None
                    body = vaila_project_bytes(
                        edited,
                        project.get("viewer_state", {}),
                        project.get("analyses", {}),
                        source_name=source_name,
                        source_bytes=source_bytes,
                    )
                    self.send_bytes(200, body, "application/vnd.vaila.project+zip")
                    return
                if req_path == "/api/analyze/orientation":
                    request = json.loads(self.rfile.read(length))
                    trial = trial_from_payload(request["trial"])
                    result = marker_frame_orientations(
                        trial,
                        str(request["origin"]),
                        str(request["x_axis_point"]),
                        str(request["xy_plane_point"]),
                        sequences=tuple(request.get("sequences", TAIT_BRYAN_SEQUENCES)),
                    )
                    self.send_bytes(
                        200,
                        json.dumps(json_compatible(result), allow_nan=False).encode(),
                        "application/json",
                    )
                    return
                if req_path == "/api/analyze/evaluate_point":
                    request = json.loads(self.rfile.read(length))
                    trial = trial_from_payload(request["trial"])
                    expr = str(request["expression"])
                    coords = evaluate_virtual_point_expression(trial, expr)
                    self.send_bytes(
                        200,
                        json.dumps(
                            {
                                "name": request.get("name", "VIRTUAL"),
                                "coords": json_compatible(coords),
                            },
                            allow_nan=False,
                        ).encode(),
                        "application/json",
                    )
                    return
                if req_path == "/api/analyze/kinematics_bases":
                    request = json.loads(self.rfile.read(length))
                    trial = trial_from_payload(request["trial"])
                    virtual_points = request.get("virtual_points", [])
                    if virtual_points:
                        trial = add_virtual_points_to_trial(trial, virtual_points)

                    s1_cfg = request["s1"]
                    s2_cfg = request["s2"]
                    sg_cfg = request.get("sg")
                    seq = str(request.get("sequence", "zxy"))

                    s1_orig = trial.marker(s1_cfg["origin"])
                    s1_prim = trial.marker(s1_cfg["primary_pt"])
                    s1_plane = trial.marker(s1_cfg["plane_pt"])
                    s1_bases, s1_valid = build_orthonormal_basis(
                        s1_orig,
                        s1_prim,
                        s1_plane,
                        primary_axis=s1_cfg.get("primary_axis", "+z"),
                        plane_axis=s1_cfg.get("plane_axis", "+y"),
                    )

                    s2_orig = trial.marker(s2_cfg["origin"])
                    s2_prim = trial.marker(s2_cfg["primary_pt"])
                    s2_plane = trial.marker(s2_cfg["plane_pt"])
                    s2_bases, s2_valid = build_orthonormal_basis(
                        s2_orig,
                        s2_prim,
                        s2_plane,
                        primary_axis=s2_cfg.get("primary_axis", "+z"),
                        plane_axis=s2_cfg.get("plane_axis", "+y"),
                    )

                    if sg_cfg and isinstance(sg_cfg, dict) and "origin" in sg_cfg:
                        sg_orig = trial.marker(sg_cfg["origin"])
                        sg_prim = trial.marker(sg_cfg["primary_pt"])
                        sg_plane = trial.marker(sg_cfg["plane_pt"])
                        sg_bases, _ = build_orthonormal_basis(
                            sg_orig,
                            sg_prim,
                            sg_plane,
                            primary_axis=sg_cfg.get("primary_axis", "+z"),
                            plane_axis=sg_cfg.get("plane_axis", "+y"),
                        )
                    elif sg_cfg and isinstance(sg_cfg, list):
                        sg_bases = np.asarray(sg_cfg, dtype=np.float64)
                    else:
                        sg_bases = None

                    kinematics = relative_segment_kinematics(
                        s1_bases, s2_bases, sg=sg_bases, sequence=seq
                    )
                    out = {
                        "s1_origin": s1_orig,
                        "s1_bases": s1_bases,
                        "s1_valid": s1_valid,
                        "s2_origin": s2_orig,
                        "s2_bases": s2_bases,
                        "s2_valid": s2_valid,
                        "sg_bases": sg_bases if sg_bases is not None else np.eye(3),
                        "MR2": kinematics["MR2"],
                        "MR": kinematics["MR"],
                        "euler": kinematics["euler"],
                        "quaternions": kinematics["quaternions"],
                        "valid": kinematics["valid"],
                        "sequence": kinematics["sequence"],
                    }
                    self.send_bytes(
                        200,
                        json.dumps(json_compatible(out), allow_nan=False).encode(),
                        "application/json",
                    )
                    return
                if req_path == "/api/analyze/import_trajectory_csv":
                    request = json.loads(self.rfile.read(length))
                    csv_text = str(request["csv_text"])
                    expected_frames = int(request.get("expected_frames", 0)) or None
                    coords = load_marker_trajectory_csv(csv_text, expected_frames=expected_frames)
                    self.send_bytes(
                        200,
                        json.dumps(
                            {
                                "coords": json_compatible(coords),
                                "frames": int(coords.shape[0]),
                            },
                            allow_nan=False,
                        ).encode(),
                        "application/json",
                    )
                    return
                if req_path == "/api/analyze/export_trajectory_csv":
                    request = json.loads(self.rfile.read(length))
                    trial = trial_from_payload(request["trial"])
                    marker_name = str(request["marker"])
                    csv_str = export_marker_trajectory_csv(trial, marker_name)
                    self.send_bytes(200, csv_str.encode("utf-8"), "text/csv")
                    return
                if req_path == "/api/analyze/blank_frames":
                    request = json.loads(self.rfile.read(length))
                    trial = trial_from_payload(request["trial"])
                    marker_name = str(request["marker"])
                    frames = request.get("frames")
                    frame_range = (
                        tuple(request["frame_range"])
                        if "frame_range" in request and request["frame_range"]
                        else None
                    )
                    csv_frames = request.get("csv_frames")
                    trial = blank_marker_frames(
                        trial,
                        marker_name,
                        frames=frames,
                        frame_range=frame_range,
                        csv_frames_source=csv_frames,
                    )
                    self.send_bytes(
                        200,
                        json.dumps(
                            {"xyz": json_compatible(trial.xyz)},
                            allow_nan=False,
                        ).encode(),
                        "application/json",
                    )
                    return
                if req_path == "/api/analyze/convert_monocular":
                    request = json.loads(self.rfile.read(length))
                    trial = trial_from_payload(request["trial"])
                    auto_floor_z = bool(request.get("auto_floor_z", True))
                    auto_center_xy = bool(request.get("auto_center_xy", True))
                    transformed_trial, R, trans = transform_trial_monocular_to_standard(
                        trial, auto_floor_z=auto_floor_z, auto_center_xy=auto_center_xy
                    )
                    out = {
                        "xyz": json_compatible(transformed_trial.xyz),
                        "R": json_compatible(R),
                        "translation": json_compatible(trans),
                    }
                    self.send_bytes(
                        200,
                        json.dumps(out, allow_nan=False).encode(),
                        "application/json",
                    )
                    return
                if req_path == "/api/analyze/dynamics":
                    dynamics_input = self.rfile.read(length)
                    with tempfile.TemporaryDirectory(prefix="openbiomech-dynamics-") as directory:
                        input_path = Path(directory) / "input.json"
                        output_path = Path(directory) / "loads.csv"
                        input_path.write_bytes(dynamics_input)
                        row_count = run_dynamics(input_path, output_path)
                        result = {"row_count": row_count, "csv": output_path.read_text()}
                    self.send_bytes(
                        200, json.dumps(result, allow_nan=False).encode(), "application/json"
                    )
                    return
                query = parse_qs(urlsplit(self.path).query)
                name = Path(query.get("name", [""])[0]).name
                suffix = Path(name).suffix.lower()
                if suffix not in (".c3d", ".csv", ".3d", ".vaila"):
                    raise ValueError("expected .c3d, .csv, .3d or .vaila")
                rate = float(query.get("rate", ["100"])[0])
                units = query.get("units", ["m"])[0]
                uploaded = self.rfile.read(length)
                if suffix == ".vaila":
                    project = read_vaila_project(uploaded)
                    trial_from_payload(project.trial)
                    current_trial[0] = project.trial
                    current_project[0] = response_project = {
                        "trial": project.trial,
                        "viewer_state": project.viewer_state,
                        "analyses": project.analyses,
                    }
                    current_source[0] = (
                        (project.source_name, project.source_bytes)
                        if project.source_name is not None and project.source_bytes is not None
                        else None
                    )
                    response = {"project": response_project}
                    self.send_bytes(
                        200, json.dumps(response, allow_nan=False).encode(), "application/json"
                    )
                    return
                with tempfile.TemporaryDirectory(prefix="openbiomech-") as directory:
                    path = Path(directory) / f"trial{suffix}"
                    path.write_bytes(uploaded)
                    payload = trial_payload(load_trial(path, rate_hz=rate, units=units), name)
                current_trial[0] = payload
                current_project[0] = None
                current_source[0] = (name, uploaded)
                self.send_bytes(
                    200, json.dumps(payload, allow_nan=False).encode(), "application/json"
                )
            except (OSError, ValueError, IndexError, KeyError, OverflowError, RuntimeError) as exc:
                self.send_bytes(400, json.dumps({"error": str(exc)}).encode(), "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, f"http://127.0.0.1:{server.server_port}/#{token}"


def serve_viewer(
    *,
    port: int = 0,
    open_browser: bool = True,
    initial_trial: MarkerTrial | None = None,
    name: str = "",
    source_path: Path | None = None,
    initial_project: VailaProject | None = None,
    initial_videos: list[Path] | None = None,
) -> None:
    initial_project_payload = (
        {
            "trial": initial_project.trial,
            "viewer_state": initial_project.viewer_state,
            "analyses": initial_project.analyses,
        }
        if initial_project
        else None
    )
    initial_payload = (
        initial_project.trial
        if initial_project
        else trial_payload(initial_trial, name)
        if initial_trial
        else None
    )
    server, url = create_server(
        port,
        initial_payload=initial_payload,
        initial_source_name=(
            initial_project.source_name
            if initial_project
            else source_path.name
            if source_path
            else None
        ),
        initial_source_bytes=(
            initial_project.source_bytes
            if initial_project
            else source_path.read_bytes()
            if source_path
            else None
        ),
        initial_project=initial_project_payload,
        source_dir=source_path.parent if source_path and source_path.is_file() else None,
        initial_videos=initial_videos,
    )
    print(f"mkvis3d: {url}", flush=True)
    print("Use File > Shut Down mkvis3d in the viewer or press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
