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

from .marker_trial import MarkerTrial
from .model import Landmark, Segment, landmark_from_trial
from .trial_io import load_trial


def _load_trial(path: Path, *, rate_hz: float = 100.0, units: str = "m") -> MarkerTrial:
    return load_trial(path, rate_hz=rate_hz, units=units)


def _cmd_view(args: argparse.Namespace) -> int:
    from .viewer import export_viewer

    if args.path.resolve() == args.output.resolve():
        raise ValueError("output must differ from the input file")
    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    export_viewer(trial, args.path.name, args.output)
    print(f"viewer: {args.output.resolve()}")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from .viewer import serve_viewer

    serve_viewer(port=args.port, open_browser=not args.no_browser)
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from .analysis_io import write_demo

    write_demo(args.output)
    print(f"synthetic trial: {args.output}")
    return 0


def _cmd_dynamics(args: argparse.Namespace) -> int:
    from .analysis_io import run_dynamics

    if args.path.resolve() == args.output.resolve():
        raise ValueError("output must differ from the input file")
    rows = run_dynamics(args.path, args.output)
    print(f"dynamics: {rows} rows -> {args.output}")
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    print(f"file:     {args.path}")
    print(f"frames:   {trial.n_frames}")
    print(f"markers:  {trial.n_markers}")
    print(f"rate:     {trial.rate_hz:g} Hz")
    print(f"labels:   {', '.join(trial.labels)}")
    return 0


def _cmd_segment(args: argparse.Namespace) -> int:
    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
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
        description="mkvis3d / OpenBiomech — motion viewer and reproducible biomechanics.",
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

    p_view = sub.add_parser("view", help="export a standalone interactive HTML movement viewer")
    p_view.add_argument("path", type=Path)
    p_view.add_argument("--output", "-o", type=Path, required=True)
    p_view.set_defaults(func=_cmd_view)
    for p in (p_info, p_segment, p_view):
        p.add_argument(
            "--rate",
            type=float,
            default=100.0,
            help="CSV/.3d sampling rate in Hz (default: 100); C3D uses metadata",
        )
        p.add_argument(
            "--units",
            choices=("m", "cm", "mm"),
            default="m",
            help="CSV/.3d coordinate units; C3D uses metadata",
        )
    p_gui = sub.add_parser("gui", help="open the local visual interface for C3D/CSV/.3d files")
    p_gui.add_argument("--port", type=int, default=0, help="local port (0 chooses a free port)")
    p_gui.add_argument(
        "--no-browser", action="store_true", help="print the URL without launching a browser"
    )
    p_gui.set_defaults(func=_cmd_gui)
    p_demo = sub.add_parser("demo", help="write a synthetic four-segment dynamics trial (JSON)")
    p_demo.add_argument("--output", "-o", type=Path, required=True)
    p_demo.set_defaults(func=_cmd_demo)
    p_dynamics = sub.add_parser(
        "dynamics", help="run inverse dynamics from synchronized SI-unit JSON; export CSV"
    )
    p_dynamics.add_argument("path", type=Path)
    p_dynamics.add_argument("--output", "-o", type=Path, required=True)
    p_dynamics.set_defaults(func=_cmd_dynamics)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
