"""Tests for browser-safe video probe / H.264 re-encode helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from openbiomech.video_compat import (
    ensure_browser_video,
    is_browser_safe_codec,
    probe_video_codec,
    transcode_to_h264,
)


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(not _have_ffmpeg(), reason="ffmpeg/ffprobe required")


def _make_mpeg4_part2(path: Path) -> None:
    """Tiny MPEG-4 Part 2 (mp4v) clip — rejected by Chromium HTML5 video."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=10",
        "-t",
        "0.5",
        "-c:v",
        "mpeg4",
        "-q:v",
        "5",
        "-an",
        "-hide_banner",
        "-nostats",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def test_mpeg4_part2_is_not_browser_safe(tmp_path: Path) -> None:
    src = tmp_path / "overlay_mp4v.mp4"
    _make_mpeg4_part2(src)
    probe = probe_video_codec(src)
    assert probe["codec_name"] == "mpeg4"
    assert not is_browser_safe_codec(probe["codec_name"], probe["codec_tag_string"])


def test_ensure_browser_video_reencodes_mpeg4(tmp_path: Path) -> None:
    src = tmp_path / "overlay_mp4v.mp4"
    _make_mpeg4_part2(src)
    playable, info = ensure_browser_video(src)
    assert info["transcoded"] is True
    assert playable != src
    assert playable.is_file()
    assert playable.name == "overlay_mp4v_compress.mp4"
    assert playable.parent == src.parent
    out = probe_video_codec(playable)
    assert out["codec_name"] == "h264"
    assert is_browser_safe_codec(out["codec_name"], out["codec_tag_string"])
    # Second call hits cache
    playable2, info2 = ensure_browser_video(src)
    assert playable2 == playable
    assert info2["transcoded"] is True
    assert info2.get("cached") is True


def test_transcode_to_h264_writes_output(tmp_path: Path) -> None:
    src = tmp_path / "in.mp4"
    out = tmp_path / "out_h264.mp4"
    _make_mpeg4_part2(src)
    transcode_to_h264(src, out, use_gpu=False)
    assert out.is_file() and out.stat().st_size > 0
    assert probe_video_codec(out)["codec_name"] == "h264"
