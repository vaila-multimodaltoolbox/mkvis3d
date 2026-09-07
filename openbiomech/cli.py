"""Minimal command-line entry point for the Python prototype.

`README.md`'s `pipeline-cli` crate (full command-driven analysis pipeline,
config templates, batch processing) is not started — see `CLAUDE.md`'s
crate table. This is a thin, hand-scoped CLI over what already exists
(`c3d_io`, `csv_io`, `model.landmark`/`segment`) so the prototype can be run
as a program instead of only imported in tests, nothing more.

Usage:
    uv run openbiomech info data/trial.c3d
    uv run openbiomech segment data/trial.c3d p1 p5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .c3d_io import read_c3d_native
from .csv_io import read_wide_csv
from .marker_trial import MarkerTrial
from .model import Landmark, Segment, landmark_from_trial


def _load_trial(path: Path) -> MarkerTrial:
    suffix = path.suffix.lower()
    if suffix == ".c3d":
        return read_c3d_native(path)
    if suffix in (".csv", ".3d"):
        return read_wide_csv(path)
    raise ValueError(f"{path}: unrecognized extension {suffix!r} (expected .c3d, .csv, or .3d)")


def _cmd_info(args: argparse.Namespace) -> int:
    trial = _load_trial(args.path)
    print(f"file:     {args.path}")
    print(f"frames:   {trial.n_frames}")
    print(f"markers:  {trial.n_markers}")
    print(f"rate:     {trial.rate_hz:g} Hz")
    print(f"labels:   {', '.join(trial.labels)}")
    return 0


def _cmd_segment(args: argparse.Namespace) -> int:
    trial = _load_trial(args.path)
    proximal: Landmark = landmark_from_trial(trial, args.proximal)
    distal: Landmark = landmark_from_trial(trial, args.distal)
    seg = Segment(name=f"{args.proximal}-{args.distal}", proximal=proximal, distal=distal)

    length = seg.length()
    axis = seg.longitudinal_axis()
    valid = ~((length != length) | (length == 0.0))  # not NaN, not zero
    n_valid = int(valid.sum())

    print(f"segment:      {seg.name}")
    print(f"frames:       {seg.n_frames}  ({n_valid} with a defined length/axis)")
    if n_valid == 0:
        print("length:       undefined every frame (occluded or coincident markers)")
        return 0
    print(f"length mean:  {length[valid].mean():.4f} m")
    print(f"length range: {length[valid].min():.4f} - {length[valid].max():.4f} m")
    print(f"axis (frame 0 with a defined value): {axis[valid][0]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openbiomech",
        description="OpenBiomech Python prototype CLI — c3d_io/csv_io + model inspection.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="print trial metadata (frames, markers, rate, labels)")
    p_info.add_argument("path", type=Path, help="path to a .c3d, .csv, or .3d trial file")
    p_info.set_defaults(func=_cmd_info)

    p_segment = sub.add_parser(
        "segment", help="compute length + longitudinal axis for one proximal/distal marker pair"
    )
    p_segment.add_argument("path", type=Path, help="path to a .c3d, .csv, or .3d trial file")
    p_segment.add_argument("proximal", help="proximal marker label, e.g. p1")
    p_segment.add_argument("distal", help="distal marker label, e.g. p5")
    p_segment.set_defaults(func=_cmd_segment)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
