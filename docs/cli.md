# mkvis3d CLI Reference

Entry point: `openbiomech/cli.py` (`build_parser()`). Installed as two console
scripts (same code): `mkvis3d` and `openbiomech`. Run either through `uv run`,
or invoke `mkvis3d.py` / the standalone binary directly (see
[README.md — Running mkvis3d](../README.md#running-mkvis3d)).

```bash
uv run mkvis3d <command> [args...]
# equivalent:
uv run openbiomech <command> [args...]
uv run python -m openbiomech.cli <command> [args...]
```

All commands accept `.c3d`, `.csv`, or `.3d` (wide per-marker CSV) trial
files. `info`, `segment`, `view`, `gui`, `blender`, and `bvh` additionally
accept `--rate` (Hz, default `100.0`) and `--units` (`m`/`cm`/`mm`, default
`m`) for **CSV/.3d** input — a C3D file's own header/`POINT:UNITS`
metadata is used instead and these two flags are ignored for it.

## `info`

Print trial metadata: frame count, marker count, sampling rate, marker
labels.

```bash
uv run mkvis3d info data/rec3d_20260826_121305_m.c3d
```

| Argument | Description |
|---|---|
| `path` | Trial file (`.c3d`, `.csv`, `.3d`) |

## `segment`

Compute segment length and longitudinal axis for one proximal/distal marker
pair (see `openbiomech/model/segment.py`).

```bash
uv run mkvis3d segment data/trial.c3d p1 p5
```

| Argument | Description |
|---|---|
| `path` | Trial file |
| `proximal` | Proximal marker label, e.g. `p1` |
| `distal` | Distal marker label, e.g. `p5` |

## `view`

Export a standalone, self-contained interactive HTML movement viewer (no
server, no CDN — see `openbiomech/viewer.py`/`.html`/`.js`).

```bash
uv run mkvis3d view data/trial.c3d --output trial_viewer.html
```

| Argument | Description |
|---|---|
| `path` | Trial file |
| `--output`, `-o` | Output HTML path (default: `<input>_viewer.html`) |

## `gui`

Start the local, loopback-only web viewer (stdlib `http.server`) and open it
in the default browser. Supports C3D/CSV/.3d file upload from the browser,
playback, orbit/pan/zoom, distance measurement, real-time charts, force
platform / GRF overlays, and CSV/HTML export.

```bash
uv run mkvis3d gui                       # empty viewer, pick a file in the browser
uv run mkvis3d gui data/trial.c3d        # load a file immediately
uv run mkvis3d gui --port 8765 --no-browser
```

| Argument | Description |
|---|---|
| `path` | Optional motion file to load immediately |
| `--port` | Local port (`0` = choose a free port) |
| `--no-browser` | Print the URL instead of launching a browser |

## `blender`

Export the trial to an executable Blender Python script that reconstructs
the animated markers/skeleton when run inside Blender (`Scripting` tab, or
`blender --background --python out.py`). See `blender_addon/openbiomech_blender.py`
and `skeleton_templates/` for supported marker-set templates.

```bash
uv run mkvis3d blender data/trial.c3d --output trial_blender.py --skeleton mediapipe_pose33
```

| Argument | Description |
|---|---|
| `path` | Trial file |
| `--output`, `-o` | Output `.py` script path (required) |
| `--skeleton`, `-s` | Skeleton template name (see `skeleton_templates/`) |

## `bvh`

Export the trial to a standard Biovision Hierarchy (`.bvh`) motion capture
file.

```bash
uv run mkvis3d bvh data/trial.c3d --output trial.bvh
```

| Argument | Description |
|---|---|
| `path` | Trial file |
| `--output`, `-o` | Output BVH path (required) |

## `demo`

Write a synthetic four-segment inverse-dynamics trial (SI-unit JSON) for
testing the `dynamics` command without real capture data.

```bash
uv run mkvis3d demo --output demo_trial.json
```

| Argument | Description |
|---|---|
| `--output`, `-o` | Output JSON path (required) |

## `dynamics`

Run recursive Newton-Euler inverse dynamics from a synchronized SI-unit
JSON trial (as produced by `demo`, or hand-built per
`openbiomech/analysis_io.py`) and export a CSV of per-frame kinetics.

```bash
uv run mkvis3d dynamics demo_trial.json --output dynamics.csv
```

| Argument | Description |
|---|---|
| `path` | Input JSON trial |
| `--output`, `-o` | Output CSV path (required) |

## `lcs`

Transform a trial into the canonical Visual3D-style Laboratory Coordinate
System, given the trial's actual anteroposterior and axial (vertical)
directions.

```bash
uv run mkvis3d lcs data/trial.c3d --ap +Y --axial +Z --output trial_lcs.csv
uv run mkvis3d lcs data/trial.c3d --ap +Y --axial +Z --output trial_lcs.html   # viewer export instead of CSV
```

| Argument | Description |
|---|---|
| `path` | Input trial file |
| `--ap` | AP (progression) direction, e.g. `+Y`, `+Z`, `+X` (default `+Y`) |
| `--axial` | Axial (vertical-up) direction, e.g. `+Z`, `+Y` (default `+Z`) |
| `--output`, `-o` | Output path (required); `.html`/`.htm` exports a viewer, anything else writes wide CSV |

## `filter`

Gap-fill and smooth trial trajectories.

```bash
uv run mkvis3d filter data/trial.c3d --interp linear --smooth butterworth --cutoff 6.0 --output trial_filtered.csv
```

| Argument | Description |
|---|---|
| `path` | Input trial file |
| `--interp` | Gap-filling method: `none`, `linear`, `cubic`, `nearest` (default `linear`) |
| `--max-gap` | Max consecutive frames to interpolate (default `10`) |
| `--smooth` | Smoothing method: `none`, `butterworth`, `median`, `moving_average`, `hampel` (default `butterworth`) |
| `--cutoff` | Butterworth cutoff frequency, Hz (default `6.0`) |
| `--order` | Butterworth filter order (default `4`) |
| `--window` | Window size for median/moving-average/Hampel (default `5`) |
| `--output`, `-o` | Output file path (required) |

---

See [architecture.md](architecture.md) for the math each command implements,
and [../README.md](../README.md) for install/build instructions.
