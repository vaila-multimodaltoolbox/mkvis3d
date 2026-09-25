"""Browser-safe video helpers: probe codecs and re-encode to H.264 via ffmpeg.

Chromium/Firefox reject MPEG-4 Part 2 (`mpeg4` / `mp4v`) in HTML5 <video>.
H.264 (`h264` / `avc1`), VP8/VP9, and AV1 are accepted. When a reference
video is not browser-safe, re-encode once to a sibling cache file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# Codecs HTML5 video can typically play without plugins (Chrome/Firefox/Edge).
BROWSER_SAFE_CODECS = frozenset({"h264", "avc1", "vp8", "vp9", "av1", "theora"})

CACHE_DIRNAME = ".openbiomech_h264"  # legacy; new outputs use *_compress.mp4 beside source


def which_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def which_ffprobe() -> str | None:
    return shutil.which("ffprobe")


def probe_video_codec(path: Path) -> dict[str, str | None]:
    """Return first video stream codec_name / codec_tag_string, or unknowns."""
    ffprobe = which_ffprobe()
    if not ffprobe or not path.is_file():
        return {"codec_name": None, "codec_tag_string": None}
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,codec_tag_string",
        "-of",
        "json",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"codec_name": None, "codec_tag_string": None}
    if proc.returncode != 0:
        return {"codec_name": None, "codec_tag_string": None}
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"codec_name": None, "codec_tag_string": None}
    streams = data.get("streams") or []
    if not streams:
        return {"codec_name": None, "codec_tag_string": None}
    stream = streams[0]
    return {
        "codec_name": stream.get("codec_name"),
        "codec_tag_string": stream.get("codec_tag_string"),
    }


def is_browser_safe_codec(codec_name: str | None, codec_tag: str | None = None) -> bool:
    names = {((codec_name or "").strip().lower()), ((codec_tag or "").strip().lower())}
    names.discard("")
    return bool(names & BROWSER_SAFE_CODECS)


def _nvenc_available(ffmpeg: str) -> bool:
    try:
        probe = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            return False
        test = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=1280x720:rate=30",
                "-pix_fmt",
                "yuv420p",
                "-t",
                "0.2",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return test.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def cache_path_for(source: Path, *, output_dir: Path | None = None) -> Path:
    """Sibling ``*_compress.mp4`` in the source directory (or *output_dir*)."""
    stem = source.stem
    # Avoid stem_compress_compress if re-ensuring an already-compressed file.
    out_stem = stem if stem.endswith("_compress") else f"{stem}_compress"
    return (output_dir or source.parent) / f"{out_stem}.mp4"


def _cache_fresh(source: Path, cache: Path) -> bool:
    if not cache.is_file():
        return False
    try:
        return cache.stat().st_mtime_ns >= source.stat().st_mtime_ns and cache.stat().st_size > 0
    except OSError:
        return False


def transcode_to_h264(source: Path, output: Path, *, use_gpu: bool | None = None) -> Path:
    """Encode *source* to browser-safe H.264 MP4 at *output*. Returns *output*."""
    ffmpeg = which_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH; install ffmpeg to re-encode reference video")
    if not source.is_file():
        raise FileNotFoundError(f"video not found: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    if use_gpu is None:
        use_gpu = _nvenc_available(ffmpeg)

    # Prefer GPU when available (same idea as vailá compress_videos_h264).
    if use_gpu:
        video_args = [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p5",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            "23",
        ]
    else:
        video_args = ["-c:v", "libx264", "-preset", "medium", "-crf", "23"]

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-fps_mode",
        "passthrough",
        *video_args,
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        "-hide_banner",
        "-nostats",
        str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise RuntimeError(f"ffmpeg H.264 encode failed (exit {proc.returncode}): {detail}")
    return output


def ensure_browser_video(source: Path, *, output_dir: Path | None = None) -> tuple[Path, dict]:
    """Return a browser-playable path for *source*, re-encoding when needed.

    When re-encoding, writes ``{stem}_compress.mp4`` beside the source (or in
    *output_dir* when provided). Returns ``(path, info)``.
    """
    source = source.resolve()
    probe = probe_video_codec(source)
    codec_name = probe.get("codec_name")
    codec_tag = probe.get("codec_tag_string")
    info: dict = {
        "source": str(source),
        "codec_name": codec_name,
        "codec_tag_string": codec_tag,
        "transcoded": False,
        "ffmpeg": which_ffmpeg(),
        "ffprobe": which_ffprobe(),
    }

    if is_browser_safe_codec(
        codec_name if isinstance(codec_name, str) else None,
        codec_tag if isinstance(codec_tag, str) else None,
    ):
        info["path"] = str(source)
        return source, info

    # Unknown codec (no ffprobe): try serving as-is; caller may still fail in browser.
    if codec_name is None and codec_tag is None and which_ffprobe() is None:
        info["path"] = str(source)
        info["warning"] = "ffprobe unavailable; could not verify codec"
        return source, info

    cache = cache_path_for(source, output_dir=output_dir)
    if _cache_fresh(source, cache):
        info["transcoded"] = True
        info["cached"] = True
        info["path"] = str(cache)
        return cache, info

    transcode_to_h264(source, cache)
    info["transcoded"] = True
    info["cached"] = False
    info["path"] = str(cache)
    return cache, info


def ffmpeg_suggestion(source_name: str = "input.mp4") -> str:
    stem = Path(source_name).stem
    out = f"{stem}_compress.mp4" if not stem.endswith("_compress") else f"{stem}.mp4"
    return (
        f'ffmpeg -y -i "{source_name}" -c:v libx264 -pix_fmt yuv420p '
        f'-movflags +faststart -an "{out}"'
    )


def pick_local_video_path() -> Path | None:
    """Native file dialog on the server machine (zenity / kdialog). Loopback GUI only."""
    filters_zenity = (
        "Video files | *.mp4 *.MP4 *.mov *.MOV *.mkv *.MKV *.avi *.AVI *.webm *.WEBM *.m4v *.M4V"
    )
    candidates = [
        [
            "zenity",
            "--file-selection",
            "--title=Load Reference Video",
            f"--file-filter={filters_zenity}",
        ],
        [
            "kdialog",
            "--getopenfilename",
            str(Path.home()),
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)",
        ],
    ]
    for cmd in candidates:
        if not shutil.which(cmd[0]):
            continue
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0:
            continue
        chosen = (proc.stdout or "").strip().splitlines()
        if not chosen:
            continue
        path = Path(chosen[0].strip())
        if path.is_file():
            return path.resolve()
    return None


def pick_save_path(default_path: Path, *, title: str = "Save As") -> Path | None:
    """Native save dialog on the server machine (zenity / kdialog). Loopback GUI only.

    Returns the chosen path, or None when the user cancels or no dialog tool exists.
    A cancel does not fall through to a second dialog.
    """
    default_path = default_path.expanduser()
    candidates = [
        [
            "zenity",
            "--file-selection",
            "--save",
            "--confirm-overwrite",
            f"--title={title}",
            f"--filename={default_path}",
            "--file-filter=C3D and CSV | *.c3d *.csv *.C3D *.CSV",
        ],
        [
            "kdialog",
            "--getsavefilename",
            str(default_path),
            "C3D and CSV (*.c3d *.csv)",
            "--title",
            title,
        ],
    ]
    for cmd in candidates:
        if not shutil.which(cmd[0]):
            continue
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        chosen = (proc.stdout or "").strip().splitlines()
        if not chosen:
            return None
        path = Path(chosen[0].strip()).expanduser()
        if path.name in {"", ".", ".."} or not path.parent.is_dir():
            return None
        return path
    return None
