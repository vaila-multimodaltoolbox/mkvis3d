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

import numpy as np

from .marker_trial import MarkerTrial
from .model import Landmark, Segment, landmark_from_trial
from .trial_io import load_trial


def _load_trial(path: Path, *, rate_hz: float = 100.0, units: str = "m") -> MarkerTrial:
    return load_trial(path, rate_hz=rate_hz, units=units)


def _cmd_view(args: argparse.Namespace) -> int:
    from .viewer import export_viewer

    output = args.output
    if output is None:
        output = args.path.with_name(f"{args.path.stem}_viewer.html")
    if args.path.resolve() == output.resolve():
        raise ValueError("output must differ from the input file")
    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    export_viewer(trial, args.path.name, output)
    print(f"viewer: {output.resolve()}")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from .project_io import read_vaila_project
    from .viewer import serve_viewer

    initial_trial = None
    initial_project = None
    name = ""
    if args.path:
        if args.path.suffix.lower() == ".vaila":
            initial_project = read_vaila_project(args.path)
            name = str(initial_project.trial.get("name", args.path.name))
        else:
            initial_trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
            name = args.path.name
    video_paths = [Path(v).resolve() for v in getattr(args, "video", []) if Path(v).is_file()]
    kwargs = {}
    if video_paths:
        kwargs["initial_videos"] = video_paths
    serve_viewer(
        port=args.port,
        open_browser=not args.no_browser,
        initial_trial=initial_trial,
        name=name,
        source_path=args.path if initial_project is None else None,
        initial_project=initial_project,
        **kwargs,
    )
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


def _cmd_lcs(args: argparse.Namespace) -> int:
    from .biomech_math.lcs import transform_trial_lcs
    from .csv_io import write_wide_csv
    from .viewer import export_viewer

    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    transformed, rot, ml = transform_trial_lcs(
        trial, ap_direction=args.ap, axial_direction=args.axial
    )
    output: Path = args.output
    if output.suffix.lower() in (".html", ".htm"):
        export_viewer(transformed, f"{args.path.stem}_lcs", output)
    else:
        write_wide_csv(transformed, output)
    print(f"lcs: AP={args.ap}, AXIAL={args.axial}, ML={ml} -> {output.resolve()}")
    return 0


def _cmd_filter(args: argparse.Namespace) -> int:
    from .biomech_math.filtering import process_marker_trial
    from .csv_io import write_wide_csv
    from .viewer import export_viewer

    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    processed = process_marker_trial(
        trial,
        interp_method=args.interp,
        max_gap=args.max_gap,
        smooth_method=args.smooth,
        cutoff_hz=args.cutoff,
        order=args.order,
        window_size=args.window,
    )
    output: Path = args.output
    if output.suffix.lower() in (".html", ".htm"):
        export_viewer(processed, f"{args.path.stem}_filtered", output)
    else:
        write_wide_csv(processed, output)
    print(f"filtered: interp={args.interp}, smooth={args.smooth} -> {output.resolve()}")
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    print(f"file:     {args.path}")
    print(f"frames:   {trial.n_frames}")
    print(f"markers:  {trial.n_markers}")
    print(f"rate:     {trial.rate_hz:g} Hz")
    print(f"labels:   {', '.join(trial.labels)}")
    if getattr(trial, "force_plates", None):
        print(f"force plates: {len(trial.force_plates)}")
        for fp in trial.force_plates:
            dim_x = np.linalg.norm(fp.corners[1] - fp.corners[0])
            dim_y = np.linalg.norm(fp.corners[3] - fp.corners[0])
            n_contact = int(np.sum(fp.contact))
            print(
                f"  [{fp.name}] type={fp.plate_type}, dimensions={dim_x:.2f}m x {dim_y:.2f}m, "
                f"active_contact={n_contact}/{trial.n_frames} frames"
            )
    if getattr(trial, "analog_labels", None):
        print(f"analog:   {len(trial.analog_labels)} channels @ {trial.analog_rate_hz:g} Hz")
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


def _cmd_blender(args: argparse.Namespace) -> int:
    from .blender_io import export_blender_script
    from .viewer import load_all_skeleton_templates

    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    template = None
    if getattr(args, "skeleton", None):
        all_templates = load_all_skeleton_templates()
        template = all_templates.get(args.skeleton)

    out = export_blender_script(trial, args.output, skeleton_template=template)
    print(f"blender script: {out.resolve()}")
    return 0


def _cmd_bvh(args: argparse.Namespace) -> int:
    from .blender_io import export_bvh

    trial = _load_trial(args.path, rate_hz=args.rate, units=args.units)
    out = export_bvh(trial, args.output)
    print(f"bvh: {out.resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mkvis3d",
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
    p_view.add_argument("path", type=Path, help="path to a .c3d, .csv, or .3d trial file")
    p_view.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="output HTML path (default: <input>_viewer.html)",
    )
    p_view.set_defaults(func=_cmd_view)

    p_gui = sub.add_parser(
        "gui", help="open the local visual interface for C3D/CSV/.3d or .vaila projects"
    )
    p_gui.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        help="optional motion file or complete .vaila project to load immediately",
    )
    p_gui.add_argument("--port", type=int, default=0, help="local port (0 chooses a free port)")
    p_gui.add_argument(
        "--no-browser", action="store_true", help="print the URL without launching a browser"
    )
    p_gui.add_argument(
        "--video",
        action="append",
        type=Path,
        default=[],
        help="path to reference video file (can be repeated for multiple camera views)",
    )
    p_gui.set_defaults(func=_cmd_gui)

    p_blender = sub.add_parser(
        "blender", help="export trial to an executable Blender Python script (.py)"
    )
    p_blender.add_argument("path", type=Path, help="path to a .c3d, .csv, or .3d trial file")
    p_blender.add_argument(
        "--output", "-o", type=Path, required=True, help="output Python script path"
    )
    p_blender.add_argument(
        "--skeleton",
        "-s",
        type=str,
        default=None,
        help="skeleton template name (e.g. sam3dinov3_mhr70)",
    )
    p_blender.set_defaults(func=_cmd_blender)

    p_bvh = sub.add_parser(
        "bvh", help="export trial to standard Biovision Hierarchy (.bvh) mocap file"
    )
    p_bvh.add_argument("path", type=Path, help="path to a .c3d, .csv, or .3d trial file")
    p_bvh.add_argument("--output", "-o", type=Path, required=True, help="output BVH path")
    p_bvh.set_defaults(func=_cmd_bvh)

    for p in (p_info, p_segment, p_view, p_gui, p_blender, p_bvh):
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

    p_demo = sub.add_parser("demo", help="write a synthetic four-segment dynamics trial (JSON)")
    p_demo.add_argument("--output", "-o", type=Path, required=True)
    p_demo.set_defaults(func=_cmd_demo)

    p_dynamics = sub.add_parser(
        "dynamics", help="run inverse dynamics from synchronized SI-unit JSON; export CSV"
    )
    p_dynamics.add_argument("path", type=Path)
    p_dynamics.add_argument("--output", "-o", type=Path, required=True)
    p_dynamics.set_defaults(func=_cmd_dynamics)

    p_lcs = sub.add_parser(
        "lcs", help="transform trial to canonical Visual3D Laboratory Coordinate System"
    )
    p_lcs.add_argument("path", type=Path, help="input trial file (.c3d, .csv, .3d)")
    p_lcs.add_argument("--ap", default="+Y", help="AP (progression) direction, e.g. +Y, +Z, +X")
    p_lcs.add_argument("--axial", default="+Z", help="Axial (vertical up) direction, e.g. +Z, +Y")
    p_lcs.add_argument("--output", "-o", type=Path, required=True, help="output file path")
    p_lcs.add_argument("--rate", type=float, default=100.0, help="sampling rate in Hz")
    p_lcs.add_argument("--units", choices=("m", "cm", "mm"), default="m")
    p_lcs.set_defaults(func=_cmd_lcs)

    p_filter = sub.add_parser(
        "filter", help="gap-fill and smooth trial trajectories (Butterworth, cubic, linear, etc.)"
    )
    p_filter.add_argument("path", type=Path, help="input trial file (.c3d, .csv, .3d)")
    p_filter.add_argument(
        "--interp",
        choices=("none", "linear", "cubic", "nearest"),
        default="linear",
        help="gap filling method",
    )
    p_filter.add_argument(
        "--max-gap", type=int, default=10, help="max consecutive frames to interpolate"
    )
    p_filter.add_argument(
        "--smooth",
        choices=("none", "butterworth", "median", "moving_average", "hampel"),
        default="butterworth",
        help="smoothing / filtering method",
    )
    p_filter.add_argument(
        "--cutoff", type=float, default=6.0, help="Butterworth cutoff frequency in Hz"
    )
    p_filter.add_argument("--order", type=int, default=4, help="Butterworth filter order")
    p_filter.add_argument(
        "--window", type=int, default=5, help="window size for median/MA/Hampel filter"
    )
    p_filter.add_argument("--output", "-o", type=Path, required=True, help="output file path")
    p_filter.add_argument("--rate", type=float, default=100.0, help="sampling rate in Hz")
    p_filter.add_argument("--units", choices=("m", "cm", "mm"), default="m")
    p_filter.set_defaults(func=_cmd_filter)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    known_cmds = {
        "info",
        "segment",
        "view",
        "gui",
        "demo",
        "dynamics",
        "blender",
        "bvh",
        "lcs",
        "filter",
        "-h",
        "--help",
    }
    if raw_args and raw_args[0] not in known_cmds and not raw_args[0].startswith("-"):
        candidate = Path(raw_args[0])
        if candidate.suffix.lower() in (".c3d", ".csv", ".3d") or candidate.exists():
            raw_args.insert(0, "gui")
    parser = build_parser()
    args = parser.parse_args(raw_args)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
