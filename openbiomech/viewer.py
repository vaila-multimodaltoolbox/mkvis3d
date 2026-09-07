"""Offline HTML viewer and a loopback-only motion file interface.

Stdlib HTTP and native readers; no CDN or vailá runtime dependency.
"""

from __future__ import annotations

import json
import secrets
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

from .marker_trial import MarkerTrial
from .trial_io import load_trial


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


def render_viewer(payload: dict | None = None, *, server: bool = False) -> str:
    directory = Path(__file__).parent
    data = json.dumps({"server": server, "trial": payload}, ensure_ascii=True, allow_nan=False)
    data = data.replace("<", "\\u003c")
    return (
        (directory / "viewer.html")
        .read_text(encoding="utf-8")
        .replace("__TRIAL_DATA__", data)
        .replace("__VIEWER_SCRIPT__", (directory / "viewer.js").read_text(encoding="utf-8"))
    )


def export_viewer(trial: MarkerTrial, name: str, output: Path) -> None:
    html = render_viewer(trial_payload(trial, name))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def create_server(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Bind loopback; uploads need a per-session token, never a disk path."""
    token = secrets.token_urlsafe(32)

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
            if urlsplit(self.path).path != "/":
                self.send_bytes(404, b"Not found", "text/plain")
                return
            self.send_bytes(200, render_viewer(server=True).encode(), "text/html; charset=utf-8")

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
                self.send_bytes(
                    200, json.dumps(payload, allow_nan=False).encode(), "application/json"
                )
            except (OSError, ValueError, IndexError, KeyError, OverflowError) as exc:
                self.send_bytes(400, json.dumps({"error": str(exc)}).encode(), "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, f"http://127.0.0.1:{server.server_port}/#{token}"


def serve_viewer(*, port: int = 0, open_browser: bool = True) -> None:
    server, url = create_server(port)
    print(f"mkvis3d: {url}", flush=True)
    print("Ctrl+C encerra a interface local.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
