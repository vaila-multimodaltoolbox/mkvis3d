# mkvis3d / OpenBiomech — Documentation

Documentation hub for the project. Start here.

| Doc | Markdown | HTML |
|---|---|---|
| CLI command reference (`info`, `view`, `gui`, `blender`, `bvh`, `filter`, `lcs`, `demo`, `dynamics`, `segment`) | [cli.md](cli.md) | [cli.html](cli.html) |
| Open `.vaila` project format (trial, processing state, analog data, analyses and provenance) | [vaila-format.md](vaila-format.md) | — |
| Target architecture (long-term Rust workspace + biomechanics math reference) | [architecture.md](architecture.md) | [architecture.html](architecture.html) |

For install steps, current implementation status, and citation info, see the
project **[README.md](../README.md)**. For AI-assistant conventions and the
current phase (Python prototype vs. the Rust target), see
**[CLAUDE.md](../CLAUDE.md)**.

## What is mkvis3d?

mkvis3d (package name `openbiomech`) is an open-source, reproducible
alternative to C-Motion Visual3D and BTK Mokka: a C3D/CSV/`.3d` motion
viewer plus the underlying biomechanics math (rigid-body registration,
filtering, ISB joint kinematics, body segment parameters, gait events,
inverse dynamics with force plates). It is developed as a companion project
to **[vailá — Multimodal Toolbox](https://github.com/vaila-multimodaltoolbox/vaila)**
and is intended to eventually be integrated into it as vailá's 3D
viewer/biomechanics-core module — see
[README.md § Relationship to vailá](../README.md#relationship-to-vailá).

## Project phase

The project is in the **Python prototype** phase: the core math is
implemented and tested in Python (`openbiomech/`), reusing code already
tested in production by `vailá`, before porting to the long-term Rust
workspace described in [architecture.md](architecture.md). See the status
table in [README.md](../README.md#current-status) for which parts are done.
