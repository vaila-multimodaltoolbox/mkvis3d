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

from .marker_trial import MarkerTrial
from .trial_io import load_trial


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
    return {
        "name": name,
        "labels": list(trial.labels),
        "rate_hz": float(trial.rate_hz),
        "xyz": safe.tolist(),
    }


def render_viewer(
    payload: dict | None = None,
    *,
    server: bool = False,
    skeleton_templates: dict[str, dict] | None = None,
) -> str:
    directory = Path(__file__).parent
    if skeleton_templates is None:
        skeleton_templates = load_all_skeleton_templates()
    templates_json = json.dumps(skeleton_templates, ensure_ascii=True).replace("<", "\\u003c")
    data = json.dumps({"server": server, "trial": payload}, ensure_ascii=True, allow_nan=False)
    data = data.replace("<", "\\u003c")
    return (
        (directory / "viewer.html")
        .read_text(encoding="utf-8")
        .replace("__TRIAL_DATA__", data)
        .replace("__SKELETON_TEMPLATES__", templates_json)
        .replace("__VIEWER_SCRIPT__", (directory / "viewer.js").read_text(encoding="utf-8"))
    )


def export_viewer(trial: MarkerTrial, name: str, output: Path) -> None:
    html = render_viewer(trial_payload(trial, name))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def create_server(
    port: int = 0, initial_payload: dict | None = None
) -> tuple[ThreadingHTTPServer, str]:
    """Bind loopback; uploads need a per-session token, never a disk path."""
    token = secrets.token_urlsafe(32)
    current_trial: list[dict | None] = [initial_payload]

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
                render_viewer(payload=active_payload, server=True).encode(),
                "text/html; charset=utf-8",
            )

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/trial":
                self.send_bytes(404, b"Not found", "text/plain")
                return
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_bytes(403, b'{"error":"Session token required"}', "application/json")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 256 * 1024 * 1024:
                    raise ValueError("file must be nonempty and no larger than 256 MiB")
                query = parse_qs(urlsplit(self.path).query)
                name = Path(query.get("name", [""])[0]).name
                suffix = Path(name).suffix.lower()
                if suffix not in (".c3d", ".csv", ".3d"):
                    raise ValueError("expected .c3d, .csv or .3d")
                rate = float(query.get("rate", ["100"])[0])
                units = query.get("units", ["m"])[0]
                with tempfile.TemporaryDirectory(prefix="openbiomech-") as directory:
                    path = Path(directory) / f"trial{suffix}"
                    path.write_bytes(self.rfile.read(length))
                    payload = trial_payload(load_trial(path, rate_hz=rate, units=units), name)
                current_trial[0] = payload
                self.send_bytes(
                    200, json.dumps(payload, allow_nan=False).encode(), "application/json"
                )
            except (OSError, ValueError, IndexError, KeyError, OverflowError) as exc:
                self.send_bytes(400, json.dumps({"error": str(exc)}).encode(), "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, f"http://127.0.0.1:{server.server_port}/#{token}"


def serve_viewer(
    *,
    port: int = 0,
    open_browser: bool = True,
    initial_trial: MarkerTrial | None = None,
    name: str = "",
) -> None:
    initial_payload = trial_payload(initial_trial, name) if initial_trial else None
    server, url = create_server(port, initial_payload=initial_payload)
    print(f"mkvis3d: {url}", flush=True)
    print("Press Ctrl+C to stop the local viewer.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
