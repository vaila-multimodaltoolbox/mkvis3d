import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from threading import Thread

import pytest

from openbiomech.trial_io import load_trial
from openbiomech.viewer import create_server, trial_payload


def test_video_sync_and_multicamera_live(tmp_path):
    node = shutil.which("node")
    chrome = shutil.which("google-chrome") or "/opt/google/chrome/chrome"
    if not node or not Path(chrome).exists():
        pytest.skip("node or chrome not installed")

    video_dir = Path("/home/preto/data/dev_editc3d_apagar/c3d")
    c3d_file = video_dir / "rec3d_20260826_113736_m_meta.c3d"
    if not c3d_file.is_file():
        pytest.skip(f"Test fixture {c3d_file} not found")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        cdp_port = s.getsockname()[1]

    proc = subprocess.Popen(
        [
            chrome,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={tmp_path / 'chrome'}",
            f"--remote-debugging-port={cdp_port}",
            "--noerrdialogs",
            "--ozone-platform=headless",
            "--ozone-override-screen-size=1440,1050",
            "--use-angle=swiftshader-webgl",
            "--autoplay-policy=no-user-gesture-required",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    trial = load_trial(c3d_file)
    payload = trial_payload(trial, c3d_file.name)
    server, url = create_server(0, initial_payload=payload, source_dir=video_dir)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{cdp_port}/json/list", timeout=1
                ) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.fail("Chrome CDP did not become ready in time")

        root = Path(__file__).resolve().parent.parent
        env = dict(os.environ, CDP_PORT=str(cdp_port))
        res = subprocess.run(
            ["node", str(root / "tests/video_smoke.mjs"), str(root), url],
            env=env,
            capture_output=True,
            text=True,
        )
        print("STDOUT:\n", res.stdout)
        print("STDERR:\n", res.stderr)
        assert res.returncode == 0, f"video smoke failed: {res.stderr}\n{res.stdout}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
