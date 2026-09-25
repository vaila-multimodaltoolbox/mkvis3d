"""Build the kiki49 YOLO-Pose soccer-field dataset from every FIFA source.

    uv run python -m openbiomech.soccer_field.build_kiki49 [--sources ...] [--limit N] [--out DIR]

Sources (``sources/``) turn their native annotations into ``Sample`` objects
with complete 49-point labels; this module fans them out over processes,
de-duplicates images, checks that no match/clip group spans two splits, and
writes a self-contained Ultralytics layout (images copied, so the dataset
can move to any disk, exFAT included), a manifest, the cameras
used, the FIFA tracking benchmark, a build report and preview overlays.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np

from .camera import in_view, project
from .kiki49 import CSV_PATH, N_KPT, goal_frames, ground_lines, load_kiki49
from .label_io import format_label, write_data_yaml
from .sample import ORIGIN_ANNOTATED, ORIGIN_CAMERA, ORIGIN_PLANE, Reject, Sample, project_plane
from .sources import Options, Tracking

SOURCE_MODULES = ("fifa", "martinjolif", "soccernet", "homography", "processados")
# Lower wins when two sources hold the same image.
PRIORITY = {
    "martinjolif": 0,
    "vaila_manual": 0,
    "vaila_goal": 0,
    "soccernet": 1,
    "fifa_video": 2,
    "wc14": 3,
    "ts_worldcup": 3,
}
SPLITS = ("train", "val", "test")
DEFAULT_OUT = Path("/media/preto/Paulo/kiki49_dataset")
PREVIEWS_PER_SOURCE = 16
GENERATED_DIRS = ("images", "labels", "preview", "tracking_eval", "reports")


def _init_worker() -> None:
    cv2.setNumThreads(1)


def _run(module: str, opts: Options, task) -> list[tuple[Sample | Reject | Tracking, str]]:
    mod = importlib.import_module(f"{__package__}.sources.{module}")
    out = []
    for item in mod.process(task, opts):
        digest = ""
        if isinstance(item, Sample) and item.image is not None:
            digest = hashlib.sha1(item.image.read_bytes()).hexdigest()
        out.append((item, digest))
    return out


def collect(modules: list[str], limit: int | None, opts: Options, workers: int):
    jobs = []
    for name in modules:
        mod = importlib.import_module(f"{__package__}.sources.{name}")
        jobs += [(name, t) for t in mod.tasks(limit)]
    print(f"{len(jobs)} tasks from {', '.join(modules)}", flush=True)
    results: list[tuple[Sample | Reject | Tracking, str]] = []
    errors: list[str] = []
    t0 = time.time()
    with ProcessPoolExecutor(workers, initializer=_init_worker) as ex:
        futures = {ex.submit(_run, name, opts, t): (name, t) for name, t in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                results += fut.result()
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the build
                errors.append(f"{futures[fut][0]} {futures[fut][1]!r}: {type(exc).__name__}: {exc}")
            if i % 500 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} tasks, {time.time() - t0:.0f} s", flush=True)
    return results, errors


def dedupe(items: list[tuple[Sample, str]]) -> tuple[list[Sample], Counter]:
    items = sorted(items, key=lambda it: (PRIORITY.get(it[0].source, 9), it[0].source, it[0].uid))
    seen_path: set[str] = set()
    seen_hash: set[str] = set()
    kept, dropped = [], Counter()
    for s, digest in items:
        path = str(Path(s.image).resolve()) if s.image is not None else ""
        if path in seen_path or (digest and digest in seen_hash):
            dropped[s.source] += 1
            continue
        seen_path.add(path)
        if digest:
            seen_hash.add(digest)
        kept.append(s)
    return kept, dropped


def check_leakage(samples: list[Sample]) -> None:
    splits: dict[str, set[str]] = defaultdict(set)
    for s in samples:
        splits[s.group].add(s.split)
    leaks = {g: sorted(v) for g, v in splits.items() if len(v) > 1}
    if leaks:
        head = list(leaks.items())[:10]
        raise SystemExit(f"split leakage in {len(leaks)} groups, e.g. {head}")


def stem(s: Sample) -> str:
    return f"{s.source}__{s.uid}"


def write_dataset(out: Path, samples: list[Sample]) -> None:
    for split in SPLITS:
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
    with (
        (out / "manifest.csv").open("w", newline="") as mf,
        (out / "cameras.jsonl").open("w") as cf,
    ):
        w = csv.writer(mf)
        w.writerow(
            [
                "split",
                "image",
                "label",
                "source",
                "group",
                "origin",
                "n_visible",
                "aux3d",
                "qa_score",
            ]
        )
        for s in samples:
            assert s.image is not None
            img = out / "images" / s.split / f"{stem(s)}{Path(s.image).suffix.lower()}"
            lab = out / "labels" / s.split / f"{stem(s)}.txt"
            shutil.copyfile(s.image, img)
            lab.write_text(format_label(s.kps, s.width, s.height) + "\n")
            origin = "".join(str(int(o)) for o in s.origin)
            w.writerow(
                [
                    s.split,
                    img.relative_to(out),
                    lab.relative_to(out),
                    s.source,
                    s.group,
                    origin,
                    int((s.kps[:, 2] > 0).sum()),
                    int(s.aux3d),
                    f"{s.qa:.4f}",
                ]
            )
            rec: dict = {"image": str(img.relative_to(out)), "width": s.width, "height": s.height}
            if s.H is not None:
                rec["H"] = s.H.tolist()
            if s.camera is not None:
                rec["camera"] = s.camera.to_json()
            cf.write(json.dumps(rec) + "\n")
    shutil.copyfile(CSV_PATH, out / "keypoints_kiki49.csv")
    write_data_yaml(out)


def write_tracking(out: Path, tracks: list[Tracking]) -> None:
    d = out / "tracking_eval"
    d.mkdir(parents=True, exist_ok=True)
    header = ["frame"] + [f"p{k}_{a}" for k in range(N_KPT) for a in ("x", "y")]
    for t in tracks:
        with (d / f"{t.seq}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            for r in sorted(t.rows):
                w.writerow([int(r[0])] + ["" if not np.isfinite(v) else f"{v:.2f}" for v in r[1:]])


_ORIGIN_COLOR = {
    ORIGIN_ANNOTATED: (0, 255, 0),
    ORIGIN_PLANE: (0, 220, 255),
    ORIGIN_CAMERA: (255, 200, 0),
}


def draw_preview(s: Sample) -> np.ndarray | None:
    img = cv2.imread(str(s.image))
    if img is None:
        return None
    use_cam = s.camera is not None and (s.camera.dist is not None or s.H is None)
    polys = list(ground_lines(0.5)) + (list(goal_frames()) if s.aux3d else [])
    for poly in polys:
        if use_cam or poly[:, 2].any():
            if s.camera is None:
                continue
            uv, depth = project(poly, s.camera)
        else:
            assert s.H is not None
            uv, depth = project_plane(s.H, poly[:, :2], s.width, s.height)
        ok = in_view(uv, depth, s.width, s.height)
        for a, b, oa, ob in zip(uv[:-1], uv[1:], ok[:-1], ok[1:], strict=True):
            if oa and ob:
                cv2.line(
                    img,
                    tuple(np.round(a).astype(int)),
                    tuple(np.round(b).astype(int)),
                    (0, 0, 255),
                    1,
                    cv2.LINE_AA,
                )
    for k, (x, y, v) in enumerate(s.kps):
        if v <= 0:
            continue
        p = (int(round(x)), int(round(y)))
        cv2.circle(img, p, 6, _ORIGIN_COLOR[int(s.origin[k])], 2, cv2.LINE_AA)
        cv2.putText(
            img,
            str(k),
            (p[0] + 7, p[1] - 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        img,
        f"{s.source} {s.uid} qa={s.qa:.2f} aux3d={int(s.aux3d)}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
    )
    if s.width > 1280:
        img = cv2.resize(
            img, (1280, round(s.height * 1280 / s.width)), interpolation=cv2.INTER_AREA
        )
    return img


def write_previews(out: Path, samples: list[Sample]) -> None:
    by_source: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        by_source[s.source].append(s)
    for source, group in by_source.items():
        d = out / "preview" / source
        d.mkdir(parents=True, exist_ok=True)
        pick = sorted(group, key=lambda s: hashlib.sha1(s.uid.encode()).hexdigest())[
            :PREVIEWS_PER_SOURCE
        ]
        for s in pick:
            img = draw_preview(s)
            if img is not None:
                cv2.imwrite(str(d / f"{stem(s)}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def _pct(values: list[float]) -> str:
    v = np.array([x for x in values if np.isfinite(x)])
    if len(v) == 0:
        return "-"
    p = np.percentile(v, [10, 50, 90])
    return f"{p[0]:.2f} / {p[1]:.2f} / {p[2]:.2f} (n={len(v)})"


def write_report(
    out: Path,
    samples: list[Sample],
    rejects: list[Reject],
    dropped: Counter,
    errors: list[str],
    opts: Options,
    argv: list[str],
) -> Path:
    names = load_kiki49().names
    sources = sorted({s.source for s in samples} | {r.source for r in rejects})
    by_src: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        by_src[s.source].append(s)
    rej: dict[str, Counter] = defaultdict(Counter)
    for r in rejects:
        rej[r.source][r.reason] += 1

    L = [
        "# kiki49 build report",
        "",
        f"Command: `{' '.join(argv)}`  ",
        f"Options: aux3d={opts.aux3d}, tau={opts.tau}",
        "",
        "## Accepted images",
        "",
        "| source | train | val | test | rejected | duplicates | reject reasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for src in sources:
        n = Counter(s.split for s in by_src[src])
        reasons = ", ".join(f"{k} {v}" for k, v in rej[src].most_common())
        L.append(
            f"| {src} | {n['train']} | {n['val']} | {n['test']} | {sum(rej[src].values())} | {dropped[src]} | {reasons} |"
        )
    tot = Counter(s.split for s in samples)
    L.append(
        f"| **total** | {tot['train']} | {tot['val']} | {tot['test']} | {len(rejects)} | {sum(dropped.values())} | |"
    )

    L += ["", "## Keypoint provenance (visible labels: annotated / plane / camera)", ""]
    L += [
        "| source | annotated | plane | camera | mean visible | aux3d images |",
        "|---|---|---|---|---|---|",
    ]
    for src in sources:
        o = np.concatenate([s.origin for s in by_src[src]]) if by_src[src] else np.zeros(0)
        vis = [int((s.kps[:, 2] > 0).sum()) for s in by_src[src]]
        aux = sum(s.aux3d for s in by_src[src])
        L.append(
            f"| {src} | {int((o == ORIGIN_ANNOTATED).sum())} | {int((o == ORIGIN_PLANE).sum())} | "
            f"{int((o == ORIGIN_CAMERA).sum())} | {np.mean(vis) if vis else 0:.1f} | {aux} |"
        )

    L += ["", "## Per-keypoint visible counts", ""]
    L += ["| kp | name | " + " | ".join(sources) + " |", "|---|---|" + "---|" * len(sources)]
    for k in range(N_KPT):
        cells = [str(sum(int(s.kps[k, 2] > 0) for s in by_src[src])) for src in sources]
        L.append(f"| {k} | {names[k]} | " + " | ".join(cells) + " |")

    L += ["", "## Quality statistics (p10 / p50 / p90, accepted images)", ""]
    keys = sorted({k for s in samples for k in s.stats})
    L += ["| source | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    for src in sources:
        cells = [_pct([s.stats[k] for s in by_src[src] if k in s.stats]) for k in keys]
        L.append(f"| {src} | " + " | ".join(cells) + " |")
    L += [
        "",
        "Units: `res_med`/`res_p90`/`click_residual`/`click_agreement`/`cam_disagreement`/`post_top_err`"
        " are pixels at 1280 px width; `support` is the fraction of projected markings on white paint;"
        " `legacy_arc` counts clicks of points 10/11/18/19 on the old goal-area-y position (dropped, re-projected).",
    ]
    if any("support" in r.stats for r in rejects):
        L += ["", "## Rejected images: support (p10 / p50 / p90)", ""]
        for src in sources:
            vals = [r.stats["support"] for r in rejects if r.source == src and "support" in r.stats]
            if vals:
                L.append(f"- {src}: {_pct(vals)}")

    manual = [
        s
        for s in [*by_src.get("vaila_manual", []), *rejects]
        if s.source == "vaila_manual" and "click_agreement" in s.stats
    ]
    if manual:
        L += [
            "",
            "## FIFA tracked camera vs manual clicks (median px at 1280, per sequence, all clicked frames)",
            "",
        ]
        per_seq: dict[str, list[float]] = defaultdict(list)
        for s in manual:
            per_seq[s.uid.rsplit("_f", 1)[0]].append(s.stats["click_agreement"])
        for seq, v in sorted(per_seq.items()):
            L.append(f"- {seq}: {_pct(v)}")
    if errors:
        L += ["", f"## Errors ({len(errors)})", ""] + [f"- `{e}`" for e in errors[:50]]
    path = out / "reports" / "build_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--sources", nargs="+", choices=SOURCE_MODULES, default=list(SOURCE_MODULES))
    ap.add_argument(
        "--limit", type=int, default=None, help="cap per source split / FIFA sequence (pilot runs)"
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--no-aux3d", action="store_true", help="never label posts tops / net ground / flag tops"
    )
    ap.add_argument(
        "--tau", type=float, default=Options.tau, help="minimum line support of projected labels"
    )
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args(argv)

    out = args.out.resolve()
    for d in GENERATED_DIRS:
        shutil.rmtree(out / d, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    opts = Options(aux3d=not args.no_aux3d, tau=args.tau, frames_dir=out / "frames")

    results, errors = collect(args.sources, args.limit, opts, args.workers)
    samples = [(r, d) for r, d in results if isinstance(r, Sample)]
    rejects = [r for r, _ in results if isinstance(r, Reject)]
    tracks = [r for r, _ in results if isinstance(r, Tracking)]
    kept, dropped = dedupe(samples)
    check_leakage(kept)
    kept.sort(key=lambda s: (s.split, s.source, s.uid))

    write_dataset(out, kept)
    write_tracking(out, tracks)
    write_previews(out, kept)
    report = write_report(
        out, kept, rejects, dropped, errors, opts, ["build_kiki49", *(argv or sys.argv[1:])]
    )
    print(
        f"{len(kept)} images ({Counter(s.split for s in kept)}), {len(rejects)} rejected, {len(errors)} errors"
    )
    print(f"report: {report}")


if __name__ == "__main__":
    main()
