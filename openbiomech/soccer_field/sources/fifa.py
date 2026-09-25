"""FIFA Skeletal Tracking Challenge 2026 videos: manual clicks and dense tracked frames.

One task per sequence, decoded once, yields two sources:

* ``vaila_manual`` - the frames clicked in vailá (``vaila_dataset_v2/<who>/<clip>/<SEQ>_markers.csv``,
  one row per frame, ``p0..p31`` x/y, sparse), upgraded by ``clicks.clicks_to_sample``
  with the tracked camera of that frame;
* ``fifa_video`` - every ``STRIDE``-th frame labelled by the starter-kit camera
  tracker (``outputs/calibration/<SEQ>.npz``: per-frame K, k, R, t; world frame =
  kiki frame), projected with distortion as in the starter kit's
  ``lib/camera_tracker.py::_project_pitch_points``.

Dense frames must pass line support, a jump check (median motion of the
projected pitch between consecutive frames) and must not lie within
``AGREEMENT_WINDOW`` frames of a clicked frame where the tracker disagrees with
the clicks. Test sequences also produce a per-frame tracking benchmark.
Splits are by match (the first two team codes), fixed by hand.
"""

from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

from ..camera import Camera, in_view, project
from ..kiki49 import N_KPT, load_kiki49
from ..label_io import MIN_VISIBLE
from ..line_support import line_distance_map, support_score
from ..sample import Reject, Sample, complete_keypoints
from . import FIFA_ROOT, Options, Tracking
from .clicks import MAX_AGREEMENT, as_annotated, camera_agreement, clicks_to_sample

SOURCE_CLICKS = "vaila_manual"
SOURCE_VIDEO = "fifa_video"
MANUAL = FIFA_ROOT / "vaila_dataset_v2"
VIDEOS = FIFA_ROOT / "FIFA_Challenge_2026_Video_Data" / "Videos"
CALIBRATION = FIFA_ROOT / "FIFA-Skeletal-Tracking-Starter-Kit-2026" / "outputs" / "calibration"

TEST_MATCHES = {"NET_ARG"}
VAL_MATCHES = {"FRA_MOR"}
NO_DENSE = {"BRA_KOR_230503"}  # the tracker loses the pitch for most of the clip
STRIDE = 5
AGREEMENT_WINDOW = 25  # frames dropped around a clicked frame the tracker disagrees with
MAX_JUMP = 0.025  # of the width: median motion of the projected pitch between consecutive frames


def match_of(seq: str) -> str:
    return "_".join(seq.split("_")[:2])


def split_of(seq: str) -> str:
    m = match_of(seq)
    return "test" if m in TEST_MATCHES else "val" if m in VAL_MATCHES else "train"


def tasks(limit: int | None) -> list[tuple[str, str, str, int | None]]:
    """(seq, video, markers csv or "", dense-frame cap per sequence)."""
    seqs: dict[str, tuple[str, str]] = {}
    for markers in sorted(MANUAL.glob("*/*/*_markers.csv")):
        seq = markers.name.removesuffix("_markers.csv")
        video = VIDEOS / f"{seq}.mp4"
        if not video.exists():
            video = markers.with_name(f"{seq}.mp4")
        seqs[seq] = (str(video), str(markers))
    for video in sorted(VIDEOS.glob("*.mp4")):
        seqs.setdefault(video.stem, (str(video), ""))
    return [(seq, v, m, limit) for seq, (v, m) in sorted(seqs.items())]


def read_markers(path: Path) -> dict[int, np.ndarray]:
    """Frame -> (32, 3) clicked pixels (v=2 where clicked)."""
    out: dict[int, np.ndarray] = {}
    with path.open(newline="") as fh:
        rows = csv.reader(fh)
        next(rows)
        for r in rows:
            clicks = np.zeros((32, 3))
            for j in range(32):
                if len(r) > 2 + 2 * j and r[1 + 2 * j] and r[2 + 2 * j]:
                    clicks[j] = float(r[1 + 2 * j]), float(r[2 + 2 * j]), 2.0
            if clicks[:, 2].any():
                out[int(r[0])] = clicks
    return out


def load_cameras(seq: str) -> list[Camera]:
    path = CALIBRATION / f"{seq}.npz"
    if not path.exists():
        return []
    z = np.load(path)
    return [
        Camera(
            z["K"][f].astype(np.float64),
            z["R"][f].astype(np.float64),
            z["t"][f].astype(np.float64),
            z["k"][f].astype(np.float64),
        )
        for f in range(len(z["K"]))
    ]


def pitch_motion(cams: list[Camera], width: int, height: int) -> np.ndarray:
    """(n,) median pixel motion of the in-view planar points from frame f-1 to f (NaN if < 4)."""
    xyz = load_kiki49().xyz
    planar = load_kiki49().planar
    prev = None
    motion = np.full(len(cams), np.nan)
    for f, cam in enumerate(cams):
        uv, depth = project(xyz, cam)
        ok = in_view(uv, depth, width, height) & planar
        if prev is not None:
            both = ok & prev[1]
            if both.sum() >= 4:
                motion[f] = float(np.median(np.hypot(*(uv[both] - prev[0][both]).T)))
        prev = (uv, ok)
    return motion


def _write_frame(img: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(f"cannot write {path}")


def process(
    task: tuple[str, str, str, int | None], opts: Options
) -> list[Sample | Reject | Tracking]:
    seq, video, markers, limit = task
    if opts.frames_dir is None:
        raise ValueError("fifa source needs Options.frames_dir")
    split, group = split_of(seq), f"fifa:{match_of(seq)}"
    clicks = read_markers(Path(markers)) if markers else {}
    cams = load_cameras(seq)
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        return [Reject(SOURCE_VIDEO, seq, "unreadable_video")]
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    dense = bool(cams) and seq not in NO_DENSE
    tracking = Tracking(seq) if dense and split == "test" else None
    motion = pitch_motion(cams, width, height) if dense else np.zeros(0)
    jump = motion > MAX_JUMP * width
    jump = jump | np.append(jump[1:], False)  # a jump taints both frames
    blocked = np.zeros(len(cams), dtype=bool)
    for f, c in clicks.items():
        if f < len(cams):
            agreement, _, _ = camera_agreement(as_annotated(c), cams[f], width)
            if agreement >= MAX_AGREEMENT:
                blocked[max(0, f - AGREEMENT_WINDOW) : f + AGREEMENT_WINDOW + 1] = True

    out: list[Sample | Reject | Tracking] = []
    n_dense = 0
    f = -1
    while cap.grab():
        f += 1
        has_cam = f < len(cams)
        want_click = f in clicks
        want_dense = (
            dense
            and has_cam
            and f % STRIDE == 0
            and not want_click
            and (limit is None or n_dense < limit)
        )
        want_track = tracking is not None and has_cam
        if not (want_click or want_dense or want_track):
            continue
        ok, img = cap.retrieve()
        if not ok:
            break
        uid = f"{seq}_f{f:05d}"
        if want_click:
            path = opts.frames_dir / seq / f"f{f:05d}.jpg"
            cam = cams[f] if has_cam else None
            got = clicks_to_sample(
                SOURCE_CLICKS, uid, split, group, clicks[f], img, path, opts, cam
            )
            if isinstance(got, Sample):
                _write_frame(img, path)
            out.append(got)
        if not (want_dense or want_track):
            continue
        cam = cams[f]
        reason = "jump" if jump[f] else "click_disagreement" if blocked[f] else ""
        qa = float("nan")
        if not reason:
            qa = support_score(line_distance_map(img), lambda X, c=cam: project(X, c))
            if not qa >= opts.tau:
                reason = "line_support"
        kps, origin = complete_keypoints(np.zeros((N_KPT, 3)), width, height, None, cam, opts.aux3d)
        if not reason and int((kps[:, 2] > 0).sum()) < MIN_VISIBLE:
            reason = "few_visible"
        if tracking is not None:
            row = np.full(2 * N_KPT, np.nan)
            if not reason:
                vis = kps[:, 2] > 0
                row.reshape(N_KPT, 2)[vis] = kps[vis, :2]
            tracking.rows.append([float(f), *row.tolist()])
        if not want_dense:
            continue
        n_dense += 1
        if reason:
            out.append(Reject(SOURCE_VIDEO, uid, reason, {"support": qa}))
            continue
        path = opts.frames_dir / seq / f"f{f:05d}.jpg"
        _write_frame(img, path)
        out.append(
            Sample(
                SOURCE_VIDEO,
                uid,
                split,
                group,
                width,
                height,
                kps,
                origin,
                path,
                None,
                cam,
                opts.aux3d,
                qa,
                {"support": qa, "motion": float(motion[f])},
            )
        )
    cap.release()
    if tracking is not None:
        out.append(tracking)
    return out
