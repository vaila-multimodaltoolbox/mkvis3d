"""martinjolif football-field-detection (Roboflow v1, pitch32 clicks) -> kiki49.

The Roboflow original (``dataset_check_ok/original/...``) is used because the
staged copy's images are gone; its label order is kiki 0-31. Roboflow's
train/valid/test splits share clips, so the group is the 6-hex clip id
prefixing every file name (``08fd33_0_10_png.rf....``) and the split is
re-drawn per group with ``hashed_split``.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..sample import Reject, Sample
from . import FIFA_ROOT, Options, hashed_split
from .clicks import clicks_to_sample

SOURCE = "martinjolif"
ROOT = FIFA_ROOT / "dataset_check_ok" / "original" / "football-field-detection_v1i_yolov5pytorch"


def tasks(limit: int | None) -> list[str]:
    labels = sorted(
        p for folder in ("train", "valid", "test") for p in (ROOT / folder / "labels").glob("*.txt")
    )
    return [str(p) for p in labels][:limit]


def read_clicks(label: Path, width: int, height: int) -> np.ndarray:
    vals = np.array(label.read_text().split()[5:], dtype=np.float64).reshape(-1, 3)
    if len(vals) != 32:
        raise ValueError(f"{label}: expected 32 keypoints, got {len(vals)}")
    clicks = vals * [width, height, 1.0]
    clicks[clicks[:, 2] <= 0] = 0.0
    return clicks


def process(task: str, opts: Options) -> list[Sample | Reject]:
    label = Path(task)
    image = label.parent.parent / "images" / f"{label.stem}.jpg"
    uid = label.stem.split(".rf.")[0]
    img = cv2.imread(str(image))
    if img is None:
        return [Reject(SOURCE, uid, "unreadable_image")]
    height, width = img.shape[:2]
    group = f"martinjolif:{uid.split('_')[0]}"
    clicks = read_clicks(label, width, height)
    return [clicks_to_sample(SOURCE, uid, hashed_split(group), group, clicks, img, image, opts)]
