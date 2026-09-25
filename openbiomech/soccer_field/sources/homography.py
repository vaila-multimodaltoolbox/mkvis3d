"""WorldCup 2014 (Homayounfar et al.) and TS-WorldCup (KpSFR): raw homographies -> kiki49.

Both store ``H`` mapping image pixels to the KpSFR yard template (114.83 x
74.37, top-left origin, y down), the convention of vailá
``vaila/fifa_dataset_builder.py`` (``_centered_meters_to_kpsfr_template``,
``_project_template_points_to_image``). The metric plane -> image homography
is ``inv(H) @ T`` with ``T`` scaling kiki metres (centred, y up) into the
template; the labels are regenerated from it rather than taken from the old
staged pitch32 labels, whose points 10/11/18/19 sit on the legacy goal-area y
and whose metric positions were off by 1-2 m.

These are fits, not clicks, so every image must pass the line-support gate.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..kiki49 import HALF_LENGTH, HALF_WIDTH
from ..label_io import MIN_VISIBLE
from ..line_support import line_distance_map, support_score
from ..sample import Reject, Sample, camera_from_plane, complete_keypoints, project_plane
from . import DATASET_ROOT, Options

TEMPLATE_W, TEMPLATE_H = 114.83, 74.37
T_METRIC_TO_TEMPLATE = np.array(
    [
        [TEMPLATE_W / (2 * HALF_LENGTH), 0.0, TEMPLATE_W / 2],
        [0.0, -TEMPLATE_H / (2 * HALF_WIDTH), TEMPLATE_H / 2],
        [0.0, 0.0, 1.0],
    ]
)
MAX_CAMERA_DISAGREEMENT = 2.0  # px at 1280

WC14 = DATASET_ROOT / "worldcup2014_nhoma" / "soccer_data" / "raw"
TSWC = DATASET_ROOT / "ts_worldcup_kpsfr" / "TS-WorldCup"


def metric_homography(H_img_to_template: np.ndarray) -> np.ndarray:
    H = np.linalg.inv(H_img_to_template) @ T_METRIC_TO_TEMPLATE
    return H / H[2, 2]


def tasks(limit: int | None) -> list[tuple[str, str, str, str, str]]:
    """(source, uid, homography path, split, group)."""
    out: list[tuple[str, str, str, str, str]] = []
    for folder, split in (("train_val", "train"), ("test", "test")):
        files = sorted((WC14 / folder).glob("*.homographyMatrix"), key=lambda p: int(p.stem))
        for f in files[:limit]:
            # No match ids are published; the official split separates matches.
            out.append(("wc14", f"{folder}_{f.stem}", str(f), split, f"wc14:{folder}:{f.stem}"))
    for split in ("train", "test"):
        clips = (TSWC / f"{split}.txt").read_text().split()
        n = 0
        for clip in clips:
            for f in sorted((TSWC / "Annotations" / "80_95" / clip).glob("IMG_*_homography.npy")):
                if limit is not None and n >= limit:
                    break
                uid = f"{clip.replace('/', '_')}_{f.stem.replace('_homography', '')}"
                out.append(("ts_worldcup", uid, str(f), split, f"tswc:{clip}"))
                n += 1
    return out


def _image_path(source: str, hpath: Path) -> Path:
    if source == "wc14":
        return hpath.with_suffix(".jpg")
    rel = hpath.relative_to(TSWC / "Annotations")
    return TSWC / "Dataset" / rel.parent / rel.name.replace("_homography.npy", ".jpg")


def process(task: tuple[str, str, str, str, str], opts: Options) -> list[Sample | Reject]:
    source, uid, hpath_s, split, group = task
    hpath = Path(hpath_s)
    H_raw = np.loadtxt(hpath) if source == "wc14" else np.load(hpath)
    image_path = _image_path(source, hpath)
    img = cv2.imread(str(image_path))
    if img is None:
        return [Reject(source, uid, "unreadable_image")]
    height, width = img.shape[:2]
    H = metric_homography(np.asarray(H_raw, dtype=np.float64).reshape(3, 3))
    qa = support_score(line_distance_map(img), lambda X: project_plane(H, X[:, :2], width, height))
    stats = {"support": qa}
    if not np.isfinite(qa) or qa < opts.tau:
        return [Reject(source, uid, "line_support", stats)]
    cam, disagreement = camera_from_plane(H, width, height)
    stats["cam_disagreement"] = disagreement
    aux3d = opts.aux3d and cam is not None and disagreement <= MAX_CAMERA_DISAGREEMENT
    kps, origin = complete_keypoints(np.zeros((49, 3)), width, height, H, cam, aux3d)
    if int((kps[:, 2] > 0).sum()) < MIN_VISIBLE:
        return [Reject(source, uid, "few_visible", stats)]
    return [
        Sample(
            source=source,
            uid=uid,
            split=split,
            group=group,
            width=width,
            height=height,
            kps=kps,
            origin=origin,
            image=image_path,
            H=H,
            camera=cam,
            aux3d=aux3d,
            qa=qa,
            stats=stats,
        )
    ]
