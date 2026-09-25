"""vailá goal-point clicks (``/media/preto/Paulo/processados``) -> kiki49.

Layout: ``<clip>/<cN>/*.png`` frames plus ``<clip>/<cN>_markers[_sequential].csv``
written by vailá getpixelvideo (``frame, p0_x, p0_y, ..., source_png``). The
clicks follow a fixed goal-relative order, "left"/"right" as seen from the pitch
facing the goal:

    p0 left post base    p1 left post top     p2 right post top   p3 right post base
    p4 net ground behind the left post        p5 net ground behind the right post
    p6 corner-flag base (pitch corner)        p7 corner-flag top

p8+ appear in fewer than 1% of rows with no fixed meaning and are ignored.

The camera comes from the clicks alone: seeded by PnP on the posts and flag
over a focal sweep (square pixels, centred principal point), then aligned to
the painted markings (``line_support.refine_camera_on_lines``). The net ground
clicks are labels only (net depth varies between stadiums). Goal clicks cannot
tell the left goal from the right one (the pitch is symmetric under a 180°
turn), so the fit uses the right goal and turns to the left one when the
camera would sit on the far (y > 0) side: broadcast cameras film from the main
stand. Frames whose fitted camera fails the line-support or click gates are
rejected rather than kept with goal points only, since unlabelled in-view
field points would teach the detector low confidence.
"""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path

import cv2
import numpy as np

from ..camera import F_MIN_REL, Camera, project, refine_camera
from ..kiki49 import HALF_LENGTH, N_KPT, ground_lines, load_kiki49
from ..label_io import MIN_VISIBLE
from ..line_support import line_distance_map, refine_camera_on_lines, support_score
from ..sample import Reject, Sample, complete_keypoints, px_scale
from . import Options, hashed_split

SOURCE = "vaila_goal"
ROOT = Path("/media/preto/Paulo/processados")

N_CLICKS = 8
# Click -> kiki point when the goal is the right one (x = +52.45; "left" seen from the pitch is +y).
RIGHT_GOAL = {0: 41, 1: 43, 2: 42, 3: 40, 4: 45, 5: 44}
FLAG_LEFT_SIDE = {6: 24, 7: 46}  # corner flag beyond the left post
FLAG_RIGHT_SIDE = {6: 29, 7: 47}
NET_CLICKS = (4, 5)  # labels only: excluded from the camera fit
MIN_FIT_CLICKS = 4
FOCAL_SWEEP = np.geomspace(0.4, 12.0, 25)  # in image widths
MAX_CLICK_RESIDUAL = 8.0  # px at 1280: median, fitted camera vs clicks
MAX_FOCAL_REL = 6.0  # image widths: longer lenses frame the goal face-on and leave depth unresolved
MAX_CLICK_OUTLIER = 25.0  # px at 1280: a single click farther than this is dropped


@cache
def rot180() -> np.ndarray:
    """kiki index of each point turned 180° about the centre spot (x, y) -> (-x, -y)."""
    xyz = load_kiki49().xyz
    turned = xyz * [-1.0, -1.0, 1.0]
    idx = np.array([int(np.argmin(np.abs(xyz - p).sum(axis=1))) for p in turned])
    if not np.allclose(xyz[idx], turned):
        raise ValueError("kiki49 geometry is not symmetric under a 180° turn")
    return idx


@cache
def markings_off_goal_line() -> tuple[np.ndarray, ...]:
    return tuple(p for p in ground_lines() if not np.allclose(np.abs(p[:, 0]), HALF_LENGTH))


def turn_camera(cam: Camera) -> Camera:
    """The same camera described in the pitch frame turned 180° about z."""
    return Camera(K=cam.K, R=cam.R @ np.diag([-1.0, -1.0, 1.0]), t=cam.t, dist=cam.dist)


def camera_centre(cam: Camera) -> np.ndarray:
    return -cam.R.T @ cam.t


def right_goal_mapping(clicks: np.ndarray) -> dict[int, int]:
    """Click index -> kiki point for the right-goal hypothesis.

    The flag side follows from where the flag base lies along the goal line
    (image line through the two post bases): before p0 or beyond p3.
    """
    ok = clicks[:, 2] > 0
    mapping = {c: k for c, k in RIGHT_GOAL.items() if ok[c]}
    if ok[6] or ok[7]:
        flag = clicks[6 if ok[6] else 7, :2]
        if not (ok[0] and ok[3]):
            return mapping
        a, b = clicks[0, :2], clicks[3, :2]
        s = float((flag - a) @ (b - a)) / float((b - a) @ (b - a))
        side = FLAG_LEFT_SIDE if s < 0.5 else FLAG_RIGHT_SIDE
        mapping |= {c: k for c, k in side.items() if ok[c]}
    return mapping


def seed_camera(X: np.ndarray, uv: np.ndarray, width: int, height: int) -> Camera | None:
    """Best PnP camera over a focal sweep (square pixels, centred principal point)."""
    best, best_err = None, np.inf
    for rel in FOCAL_SWEEP:
        f = rel * width
        K = np.array([[f, 0.0, width / 2.0], [0.0, f, height / 2.0], [0.0, 0.0, 1.0]])
        try:
            ok, rvec, tvec = cv2.solvePnP(X, uv, K, None, flags=cv2.SOLVEPNP_SQPNP)
        except cv2.error:  # degenerate clicks (e.g. two points clicked on the same pixel)
            return None
        if not ok:
            continue
        cam = Camera(K=K, R=cv2.Rodrigues(rvec)[0], t=tvec.ravel())
        got, depth = project(X, cam)
        if np.any(depth <= 0):
            continue
        err = float(np.sum((got - uv) ** 2))
        if err < best_err:
            best, best_err = cam, err
    if best is None:
        return None
    try:
        return refine_camera(best, X, uv)
    except ValueError:
        return best


def fit_camera(
    clicks: np.ndarray, img: np.ndarray, dist_map: np.ndarray | None = None
) -> tuple[Camera | None, dict[int, int], dict[str, float]]:
    """Camera (kiki frame) and click -> kiki mapping. None when the clicks do not fit."""
    height, width = img.shape[:2]
    stats: dict[str, float] = {"n_clicked": float((clicks[:, 2] > 0).sum())}
    mapping = right_goal_mapping(clicks)
    fit = [c for c in mapping if c not in NET_CLICKS]
    stats["n_fit"] = float(len(fit))
    if len(fit) < MIN_FIT_CLICKS:
        return None, mapping, stats
    xyz = load_kiki49().xyz
    X = xyz[[mapping[c] for c in fit]]
    uv = clicks[fit, :2]
    cam = seed_camera(X, uv, width, height)
    if cam is None:
        return None, mapping, stats
    if dist_map is None:
        dist_map = line_distance_map(img, grass_only=True)
    cam = refine_camera_on_lines(cam, dist_map, X, uv)
    if camera_centre(cam)[1] > 0:
        cam = turn_camera(cam)
        mapping = {c: int(rot180()[k]) for c, k in mapping.items()}
    got, _ = project(xyz[[mapping[c] for c in fit]], cam)
    err = np.hypot(*(got - uv).T) / px_scale(width)
    stats["click_residual"] = float(np.median(err))
    stats["focal_rel"] = float(cam.K[0, 0] / width)
    return cam, mapping, stats


def clicks_to_goal_sample(
    uid: str,
    split: str,
    group: str,
    clicks: np.ndarray,
    img: np.ndarray,
    image_path: Path,
    opts: Options,
) -> Sample | Reject:
    height, width = img.shape[:2]
    dist_map = line_distance_map(img, grass_only=True)
    cam, mapping, stats = fit_camera(clicks, img, dist_map)
    if cam is None:
        reason = "few_clicks" if stats["n_fit"] < MIN_FIT_CLICKS else "no_camera"
        return Reject(SOURCE, uid, reason, stats)
    if not F_MIN_REL <= stats["focal_rel"] <= MAX_FOCAL_REL:
        return Reject(SOURCE, uid, "focal", stats)
    if stats["click_residual"] > MAX_CLICK_RESIDUAL:
        return Reject(SOURCE, uid, "residual", stats)
    # The goal line is pinned by the clicks; only the other markings test the camera.
    qa = support_score(dist_map, lambda X: project(X, cam), lines=markings_off_goal_line())
    stats["support"] = qa
    if not qa >= opts.tau:
        return Reject(SOURCE, uid, "line_support", stats)

    xyz = load_kiki49().xyz
    ann = np.zeros((N_KPT, 3))
    for c, k in mapping.items():
        ann[k] = [clicks[c, 0], clicks[c, 1], 2.0]
    got, _ = project(xyz[list(mapping.values())], cam)
    err = np.hypot(*(got - clicks[list(mapping), :2]).T) / px_scale(width)
    for (c, k), e in zip(mapping.items(), err, strict=True):
        if e > MAX_CLICK_OUTLIER and c not in NET_CLICKS:
            ann[k] = 0.0
    kps, origin = complete_keypoints(ann, width, height, None, cam, opts.aux3d)
    if int((kps[:, 2] > 0).sum()) < MIN_VISIBLE:
        return Reject(SOURCE, uid, "few_visible", stats)
    return Sample(
        SOURCE,
        uid,
        split,
        group,
        width,
        height,
        kps,
        origin,
        image_path,
        None,
        cam,
        opts.aux3d,
        qa,
        stats,
    )


def read_clicks(row: dict[str, str]) -> np.ndarray:
    clicks = np.zeros((N_CLICKS, 3))
    for c in range(N_CLICKS):
        x, y = (row.get(f"p{c}_{a}") or "" for a in ("x", "y"))
        try:
            clicks[c] = [float(x), float(y), 2.0]
        except ValueError:
            continue
    clicks[~np.isfinite(clicks).all(axis=1)] = 0.0
    return clicks


def tasks(limit: int | None) -> list[str]:
    files = sorted(p for p in ROOT.glob("*/*_markers*.csv") if p.parent.parent == ROOT)
    return [str(p) for p in files][:limit]


def process(task: str, opts: Options) -> list[Sample | Reject]:
    csv_path = Path(task)
    clip = csv_path.parent.name
    cut = csv_path.name.split("_markers")[0]
    frames = csv_path.parent / cut
    group = f"processados:{clip}"
    split = hashed_split(group)
    out: list[Sample | Reject] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            png = (row.get("source_png") or "").strip()
            clicks = read_clicks(row)
            if not png or not (clicks[:, 2] > 0).any():
                continue
            image = frames / png
            uid = f"{clip}__{cut}__{Path(png).stem}".replace(" ", "_")
            img = cv2.imread(str(image))
            if img is None:
                out.append(Reject(SOURCE, uid, "unreadable_image"))
                continue
            out.append(clicks_to_goal_sample(uid, split, group, clicks, img, image, opts))
    return out
