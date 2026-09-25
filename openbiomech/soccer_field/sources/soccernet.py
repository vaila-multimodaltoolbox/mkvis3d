"""SoccerNet calibration-2023: human line annotations -> kiki49.

Official train/valid/test splits; the group is the match (``match_info.json``).
Planar points come from the annotation intersections and the fitted metric
homography; posts tops are annotated where the crossbar is. The z > 0 / net
points need a camera, estimated from the homography; images with annotated
post tops measure how far that camera is from the truth (``post_top_err``).
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from ..camera import project
from ..kiki49 import load_kiki49
from ..label_io import MIN_VISIBLE
from ..sample import Reject, Sample, camera_from_plane, complete_keypoints, px_scale
from ..soccernet_lines import parse_annotation
from . import DATASET_ROOT, Options

SOURCE = "soccernet"
ROOT = DATASET_ROOT / "soccernet_calibration_2023" / "calibration-2023"
SPLITS = {"train": "train", "valid": "val", "test": "test"}
POST_TOPS = (34, 35, 42, 43)

MAX_MEDIAN_RES = 3.0  # px at 1280: annotation vs fitted homography
MAX_P90_RES = 8.0
MIN_REDUNDANCY = 4  # residual scalars beyond the 8 homography unknowns
MAX_CAMERA_DISAGREEMENT = 2.0  # px at 1280: pinhole camera vs homography
MAX_POST_TOP_ERR = 8.0  # px at 1280: camera vs annotated post tops


def tasks(limit: int | None) -> list[tuple[str, str, str, str]]:
    out = []
    for folder, split in SPLITS.items():
        d = ROOT / folder
        info = json.loads((d / "match_info.json").read_text())
        n = 0
        for j in sorted(d.glob("*.json")):
            if not j.stem.isdigit() or not j.with_suffix(".jpg").exists():
                continue
            m = info.get(f"{j.stem}.jpg", {})
            group = "|".join(
                str(m.get(k, "")).strip() for k in ("league", "season", "match", "date")
            )
            out.append((str(j), split, group or f"unknown:{folder}:{j.stem}", folder))
            n += 1
            if limit is not None and n >= limit:
                break
    return out


def process(task: tuple[str, str, str, str], opts: Options) -> list[Sample | Reject]:
    path, split, group, folder = task
    j = Path(path)
    uid = f"{folder}_{j.stem}"
    img = cv2.imread(str(j.with_suffix(".jpg")), cv2.IMREAD_REDUCED_GRAYSCALE_2)
    if img is None:
        return [Reject(SOURCE, uid, "unreadable_image")]
    height, width = img.shape[0] * 2, img.shape[1] * 2
    lab = parse_annotation(json.loads(j.read_text()), width, height)
    stats = dict(lab.stats)
    if lab.H is None:
        return [Reject(SOURCE, uid, "no_homography", stats)]
    s = px_scale(width)
    res = lab.residual_px / s
    stats["res_med"] = float(np.median(res))
    stats["res_p90"] = float(np.percentile(res, 90))
    if len(res) < 8 + MIN_REDUNDANCY:
        return [Reject(SOURCE, uid, "underdetermined", stats)]
    if stats["res_med"] > MAX_MEDIAN_RES or stats["res_p90"] > MAX_P90_RES:
        return [Reject(SOURCE, uid, "residual", stats)]
    cam, disagreement = camera_from_plane(lab.H, width, height)
    if cam is None:
        return [Reject(SOURCE, uid, "no_camera", stats)]
    stats["cam_disagreement"] = disagreement

    aux3d = opts.aux3d and disagreement <= MAX_CAMERA_DISAGREEMENT
    tops = [k for k in POST_TOPS if lab.annotated[k, 2] > 0]
    if tops:
        uv, _ = project(load_kiki49().xyz[tops], cam)
        err = np.hypot(*(uv - lab.annotated[tops, :2]).T) / s
        stats["post_top_err"] = float(np.median(err))
        aux3d = aux3d and stats["post_top_err"] <= MAX_POST_TOP_ERR
    kps, origin = complete_keypoints(lab.annotated, width, height, lab.H, cam, aux3d)
    if int((kps[:, 2] > 0).sum()) < MIN_VISIBLE:
        return [Reject(SOURCE, uid, "few_visible", stats)]
    return [
        Sample(
            source=SOURCE,
            uid=uid,
            split=split,
            group=group,
            width=width,
            height=height,
            kps=kps,
            origin=origin,
            image=j.with_suffix(".jpg"),
            H=lab.H,
            camera=cam,
            aux3d=aux3d,
            qa=stats["res_med"],
            stats=stats,
        )
    ]
