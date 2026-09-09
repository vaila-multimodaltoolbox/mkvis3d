# mkvis3d — OpenBiomech

**Package version:** `0.0.1` (see `[project].version` in `pyproject.toml`). **Python:** 3.12.x (pinned in-repo for `uv`).

**Last updated:** 2026-09-08

<div align="center">
  <table>
    <tr>
      <th>Operating System</th>
      <th>Installation Method</th>
      <th>Status</th>
    </tr>
    <tr>
      <td><strong>🪟 Windows</strong></td>
      <td>uv (Recommended)</td>
      <td>✅ Ready</td>
    </tr>
    <tr>
      <td><strong>🐧 Linux</strong></td>
      <td>uv (Recommended)</td>
      <td>✅ Ready</td>
    </tr>
    <tr>
      <td><strong>🍎 macOS</strong></td>
      <td>uv (Recommended)</td>
      <td>✅ Ready</td>
    </tr>
  </table>
</div>

## ⚡ Install Now

```bash
git clone https://github.com/paulopreto/mkvis3d
cd mkvis3d
uv sync
uv run mkvis3d gui
```

That's the whole install: `mkvis3d` is a pure-Python prototype (NumPy/SciPy/
pandas/`ezc3d`), so there is no separate `install_*.sh` step like a
GPU-enabled project needs — `uv sync` resolves and locks everything from
`pyproject.toml`/`uv.lock`. See
[Installation and Setup](#installation-and-setup) below for double-click
launchers and standalone-binary builds.

## Introduction

Analysis of human movement is fundamental in health and sports biomechanics.
Commercial suites such as C-Motion **Visual3D** and BTK **Mokka** are the
de-facto standard for C3D-based motion capture review and processing, but
they are closed-source and license-gated. **mkvis3d** (Python package name
`openbiomech`) is an open-source, reproducible alternative: a C3D/CSV/`.3d`
motion viewer plus the underlying biomechanics math — rigid-body
registration, filtering, ISB joint kinematics, body segment parameters, gait
events, and inverse dynamics with force plates.

## Table of Contents

- [Introduction](#introduction)
- [Relationship to _vailá_](#relationship-to-vailá)
- [Current Status](#current-status)
- [Project Structure](#project-structure)
- [Installation and Setup](#installation-and-setup)
- [Running mkvis3d](#running-mkvis3d)
- [Building Standalone Executables](#building-standalone-executables)
- [Automated Testing](#automated-testing)
- [Data](#data)
- [Documentation](#documentation)
- [Citing](#citing)
- [Contribution](#contribution)
- [License](#license)

---

## Relationship to _vailá_

mkvis3d is developed by the same author as
**[_vailá_ — Multimodal Toolbox](https://github.com/vaila-multimodaltoolbox/vaila)**
and is built to eventually be integrated into it as vailá's dedicated 3D
viewer and biomechanics-core module (Frame C → **Visualization**, alongside
`Show C3D` / `Show CSV 3D`). Concretely, that means:

- Every math module ported from `vailá` cites its exact source file and
  function in its own docstring — see
  [CLAUDE.md § Reused from vailá](CLAUDE.md#reused-from-vailá). Math already
  tested in `vailá` production is reused here, not silently re-derived.
- Shared visual identity: `assets/icons/` reuses the `vailá` app icon
  (`vaila.png`/`.ico`/`.icns`) across all three platforms' launchers/binaries.
- The `data/` golden fixture is one real `vailá` `rec3d` export (see
  [Data](#data)), used to cross-validate the native C3D reader against
  `vailá`'s own CSV output.
- Until integration lands, mkvis3d ships and runs standalone (its own `uv`
  project, its own CLI, its own GUI) — it does not require a `vailá`
  checkout to build or run.

## Current Status

mkvis3d is in its **Python prototype** phase: de-risking the core math (C3D
parsing, rigid-body registration, filtering, inverse dynamics) in Python
before committing to the long-term Rust rewrite described in
[docs/architecture.md](docs/architecture.md). See
**[CLAUDE.md](CLAUDE.md)** for the authoritative, up-to-date phase statement;
the table below is a snapshot.

| Target Rust crate | Python module (today) | Status |
|---|---|---|
| `c3d-io` | `openbiomech/c3d_io/` | **Done.** Native NumPy binary parser (header, parameters, 3D + analog data, SoA layout) for Intel/VAX/MIPS, int16 and float storage. `POINT:UNITS` normalized to SI metres. Matches `ezc3d` bit-for-bit on the golden fixture. |
| `biomech-math` | `openbiomech/biomech_math/` | **Done.** Butterworth filtering, Kabsch rigid-body registration, scalar-first quaternions + Cardan extraction + SLERP, GCV smoothing splines. |
| `biomech-model` | `openbiomech/model/` | **Done.** Landmarks, segments, Grood & Suntay ISB joint kinematics, Zeni et al. gait events, Dumas/de Leva body segment parameters. |
| `inverse-dynamics` | `openbiomech/inverse_dynamics/` | **Done.** Force plate types 1-5 + COP, recursive Newton-Euler, joint power, distal-to-proximal segment chain. |
| `pipeline-cli` | `openbiomech/cli.py` | **Done** (hand-scoped, not the full target pipeline DSL). `info`, `segment`, `view`, `gui`, `blender`, `bvh`, `filter`, `lcs`, `demo`, `dynamics` — see [docs/cli.md](docs/cli.md). |
| `viewer-core` / `gui-app` | `openbiomech/viewer.{py,html,js}` | **Done.** Zero-dependency HTML5 Canvas 3D viewer: playback, processing, marker-defined quaternion/multi-sequence Euler analysis, inverse-dynamics execution, force platform/GRF overlays, analog-preserving edited C3D export, and complete open `.vaila` project save/reopen. |

## Project Structure

```bash
mkvis3d
├── CLAUDE.md / AGENTS.md / GEMINI.md   # AI assistant instructions (current phase, conventions)
├── .ai-memory/                          # Git-backed cross-harness memory (PROTOCOL.md, HANDOFF.md)
├── docs/                                # Project docs (this hub, CLI reference, target architecture)
├── mkvis3d.py                           # Main entry point (CLI + GUI; self-bootstraps into .venv)
├── run_app.py                           # Thin compatibility wrapper around mkvis3d.py
├── mkvis3d.bat / .command / _launcher.sh  # Double-clickable OS launchers
├── mkvis3d.spec                         # PyInstaller spec for standalone binaries
├── pyproject.toml / uv.lock             # uv-managed dependencies (NumPy, SciPy, pandas, ezc3d)
├── openbiomech/                         # The Python package (see table above)
│   ├── c3d_io/                          # Native C3D binary reader
│   ├── biomech_math/                    # Filtering, rigid body, rotations, splines
│   ├── model/                           # Landmarks, segments, ISB joints, events, BSP
│   ├── inverse_dynamics/                # Force plates, Newton-Euler, joint power
│   ├── cli.py                           # `mkvis3d` / `openbiomech` console script
│   ├── viewer.py / .html / .js          # Local GUI viewer (stdlib HTTP + Canvas)
│   ├── trial_io.py / csv_io.py          # File-format dispatch and CSV I/O
│   └── blender_io.py                    # Blender Python script export
├── blender_addon/                       # Standalone Blender import add-on
├── skeleton_templates/                  # Marker-set → skeleton templates (MediaPipe, COCO, OpenPose, ...)
├── scripts/                             # Build/launcher helper scripts (PyInstaller, desktop entries)
├── data/                                # Golden fixture (see Data below)
├── tests/                               # pytest suite
└── vendor/                              # Gitignored read-only reference checkouts (e.g. BTKCore)
```

**Developer quick reference:** [CLAUDE.md](CLAUDE.md) (current phase, commands,
conventions), [AGENTS.md](AGENTS.md) (memory protocol, harness-agnostic).

---

## Installation and Setup

### ⚡ Engine: Powered by _uv_

mkvis3d uses **[uv](https://github.com/astral-sh/uv)**, an extremely fast
Python package installer and resolver written in Rust — the same toolchain
as `vailá`. No separate Python distribution is required; `uv` manages Python
3.12 for you, and `uv.lock` guarantees what runs on one machine runs on
another.

```bash
# Install uv (skip if already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh        # Linux / macOS
# Windows PowerShell:
# irm https://astral.sh/uv/install.ps1 | iex

git clone https://github.com/paulopreto/mkvis3d
cd mkvis3d
uv sync            # creates .venv, installs numpy/scipy/pandas/ezc3d + dev tools
uv run mkvis3d gui
```

### Double-click launchers

Portable launcher scripts are checked into the repo root, so you don't need
to remember `uv run` once `uv sync` has run once:

- 🐧 `./mkvis3d_launcher.sh`
- 🍎 `./mkvis3d.command`
- 🪟 `mkvis3d.bat`

Each one prefers a standalone `dist/mkvis3d` binary if one has been built
(see [Building Standalone Executables](#building-standalone-executables)),
falls back to `uv run mkvis3d gui`, and finally to a bare `python3 -m
openbiomech.cli gui` if `uv` isn't on `PATH`.

---

## Running mkvis3d

### GUI (recommended)

```bash
uv run mkvis3d gui                     # open the local viewer, pick a file in the browser
uv run mkvis3d gui data/trial.c3d      # load a file immediately
```

`gui` starts a **loopback-only** local web server (stdlib `http.server`, no
external dependency) and opens it in your default browser: playback,
orbit/pan/zoom, distance measurement, real-time synced charts, force
platform / GRF vector overlays, and CSV/HTML export. C3D, CSV, and `.3d`
files can also be uploaded directly from the browser.

### CLI

```bash
uv run mkvis3d info data/rec3d_20260826_121305_m.c3d
uv run mkvis3d view data/trial.c3d --output trial_viewer.html
uv run mkvis3d filter data/trial.c3d --smooth butterworth --cutoff 6.0 --output trial_filtered.csv
uv run mkvis3d dynamics demo_trial.json --output dynamics.csv
```

Both `mkvis3d` and `openbiomech` are installed as console scripts (same
code) by `uv sync`. For the full command reference — every flag, default,
and example — see:

- **[CLI Reference (Markdown)](docs/cli.md)** · **[CLI Reference (HTML)](docs/cli.html)**

---

## Building Standalone Executables

For distributing mkvis3d to machines without Python/`uv`, a PyInstaller spec
(`mkvis3d.spec`) bundles the app (including `viewer.html`/`.js`, skeleton
templates, and icons) into a single-file binary:

```bash
uv run python scripts/build_app.py
# Linux   -> dist/mkvis3d
# macOS   -> dist/mkvis3d.app
# Windows -> dist/mkvis3d.exe
```

### Windows portable executable

On a Windows development machine, double-click `scripts\build_windows.bat`
or run the command above. Give the resulting `dist\mkvis3d.exe` to the user;
it does not require Python, `uv`, or the source tree on their computer.

The user starts mkvis3d by double-clicking the executable. A terminal window
remains open while the local viewer runs in the default browser. To finish,
choose **File → Encerrar mkvis3d** in the viewer or close the terminal window.

An unsigned build may show Microsoft Defender SmartScreen on first launch.
Only when the file came from a trusted source, the user can choose **More
info → Run anyway**. Avoiding that warning for public distribution requires
signing the executable with a trusted Windows code-signing certificate.

`.github/workflows/build_executables.yml` runs the same script on
`ubuntu-latest`/`macos-latest`/`windows-latest` for every push to `main` and
every `v*` tag, uploading `mkvis3d-linux-x86_64`,
`mkvis3d-windows-x86_64.exe`, and `mkvis3d-macos-app.zip` as build artifacts.

---

## Automated Testing

```bash
uv run pytest -v              # full suite
uv run pytest -m "not browser" -v   # skip Selenium cross-browser tests
uv run ruff check .            # lint
uv run ruff format .           # format
uv run ty check                # type check
```

The suite covers native C3D parsing against the `ezc3d` oracle and the
golden CSV fixture, every `biomech_math`/`model`/`inverse_dynamics` module
against synthetic ground truth, CLI subcommands, Blender/BVH export, and (as
`browser`-marked tests) the GUI viewer across Chrome/Chromium/Firefox via
Selenium.

---

## Data

`data/` holds one real `vailá` `rec3d` export in four parallel formats (same
trial): `.csv`/`.3d` (wide per-marker CSV, identical to each other), `.bvh`,
and `_m.c3d` (binary C3D, 70 markers `p1..p70`, 631 frames, 100 Hz, no
analog channels), plus `pilot0102_squat03.c3d` (a force-plate trial used to
test the inverse-dynamics/GRF pipeline). This is the golden fixture that
cross-validates the C3D reader against the CSV — see
`tests/test_c3d_io_golden.py`. Do not modify these files; do not add large
binary fixtures without checking size.

---

## Documentation

- **[📖 User Manual & Biomechanics Theory Guide](docs/MANUAL.md)** ([Interactive HTML](docs/manual.html)) — **complete Kwon3D & Visual3D parity guide, mathematical derivations, Cartesian bases, relative kinematics, virtual points, and practical tutorials**
- **[Documentation Hub](docs/index.md)** ([HTML](docs/index.html)) — start here
- **[CLI Reference](docs/cli.md)** ([HTML](docs/cli.html)) — every `mkvis3d` command, flags, and examples
- **[Open `.vaila` Project Format](docs/vaila-format.md)** — versioned ZIP/JSON specification for complete reproducible projects
- **[Target Architecture](docs/architecture.md)** ([HTML](docs/architecture.html)) — the long-term Rust workspace (7 crates) and the ISB/Kabsch/Butterworth/GCVSPL/force-plate/Newton-Euler math reference
- **[CLAUDE.md](CLAUDE.md)** — current phase, commands, and Python conventions for AI assistants (also read by Codex/Cursor via [AGENTS.md](AGENTS.md) and Gemini via [GEMINI.md](GEMINI.md))

---

## Citing

mkvis3d does not yet have a standalone citation — it is a pre-integration
prototype for _vailá_. Until it is merged into and released as part of
_vailá_, please cite the parent toolbox if you use mkvis3d in research:

```bibtex
@misc{vaila2024,
  title={vailá - Versatile Anarcho Integrated Liberation Ánalysis in Multimodal Toolbox},
  author={Paulo Roberto Pereira Santiago and Guilherme Manna Cesar and Ligia Yumi Mochida and Juan Aceros and others},
  year={2024},
  eprint={2410.07238},
  archivePrefix={arXiv},
  primaryClass={cs.HC},
  url={https://arxiv.org/abs/2410.07238}
}
```

See **[vailá on GitHub](https://github.com/vaila-multimodaltoolbox/vaila)** and
**[vailá on arXiv](https://arxiv.org/abs/2410.07238)** for the full citation list.

## Contribution

Contributions are welcome. Fork the repository, branch for your change, and
open a pull request. Before submitting: run `uv run pytest -v`,
`uv run ruff check .`, `uv run ruff format .`, and `uv run ty check`. Follow
the memory protocol in [`.ai-memory/PROTOCOL.md`](.ai-memory/PROTOCOL.md) and
the conventions in [`CLAUDE.md`](CLAUDE.md) — in particular, never silently
duplicate math already tested in `vailá` (check
`/home/preto/data/vaila/vaila/` first, or the public
[_vailá_ repository](https://github.com/vaila-multimodaltoolbox/vaila) if you
don't have a local checkout).

## License

This project is licensed under the GNU Affero General Public License v3.0
(AGPLv3), matching `pyproject.toml`'s `license = "AGPL-3.0-or-later"`. This
license ensures that any use of mkvis3d, including network/server usage,
maintains the freedom of the software and requires source code availability.

See <https://www.gnu.org/licenses/agpl-3.0.html> for the full license text.
