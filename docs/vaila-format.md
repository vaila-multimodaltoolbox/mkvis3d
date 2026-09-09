# `.vaila` Open Project Format

`.vaila` is OpenBiomech's open, free, non-proprietary project format. A file
is an ordinary ZIP archive and can be inspected with any ZIP/JSON tool. It
contains no pickle, executable code, encryption, DRM, or vendor-only codec.

## Media type and version

- Extension: `.vaila`
- Media type: `application/vnd.vaila.project+zip`
- Current schema: `1`
- Text encoding: UTF-8
- Numeric units: SI unless an artifact explicitly declares another unit
- Quaternion order: scalar-first `(w, x, y, z)`
- Euler/Cardan angles: sequence and units are mandatory metadata

## Archive layout

```text
project.vaila
├── manifest.json
├── trial.json
├── viewer-state.json
├── analyses.json
└── source/
    └── original.c3d        # optional; may also be CSV or .3d
```

`manifest.json` identifies `format: "vaila-project"`,
`schema_version: 1`, the media type, and each member's byte length and SHA-256
digest. Readers must reject unsupported versions, missing/checksum-invalid
members, encrypted members, path traversal, excessive member count, and
unreasonable expanded size.

## `trial.json`

The complete currently edited trial:

- `name`, `rate_hz`, marker `labels`, and `xyz` trajectories in metres;
- force-platform geometry, COP, force and contact arrays when available;
- synchronized calibrated `analog` samples as
  `[point_frame][subsample][channel]`;
- `analog_labels`, `analog_units`, and `analog_rate_hz`.

Missing numeric samples are JSON `null`, never non-standard `NaN`.

## `viewer-state.json`

Reproducible editing and visualization state, including:

- raw marker trajectories and force-platform state needed to recompute edits;
- laboratory reference-system axes;
- filter, smoothing, interpolation and outlier-processing configuration;
- active skeleton, frame, marker selections, camera, theme and display state;
- edited FPS and playback controls.

The archive stores both raw and resulting trajectories so reopening does not
apply a filter or coordinate transform twice.

## `analyses.json`

An extensible JSON object. Built-in artifacts use explicit `schema_version`,
units, marker/segment definitions and sampling rate:

- `distance`: selected marker pair and per-frame distance in metres;
- `orientations`: marker-defined rotation matrices, scalar-first quaternions,
  all selected Euler/Cardan sequences (`xyz`, `xzy`, `yxz`, `yzx`, `zxy`,
  `zyx`), and per-sequence gimbal-lock margins;
- `inverse_dynamics`: SI forces, moments, powers and model inputs/results;
- `attachments`: inert JSON or CSV analysis results, including output from
  the `openbiomech dynamics` command.

Unknown analysis keys must be preserved by readers. This allows new
biomechanical analyses without breaking schema-1 projects.

## C3D export

Saving an edited C3D writes the current markers, gaps, FPS, analog samples,
channel names, channel units and synchronized analog rate. The optional
original source inside `.vaila` remains available as provenance and for
future preservation of additional vendor-specific parameters.

## License and interoperability

The format specification and implementation are part of the AGPL-3.0-or-later
OpenBiomech project. No payment, account, cloud service, or proprietary
software is required to create, inspect or implement `.vaila` files.
