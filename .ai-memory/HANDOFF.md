# Session Handoff: Analog C3D and open .vaila projects
- **Status:** Completed
- **Current State:**
  - `MarkerTrial` now carries synchronized calibrated analog samples, labels,
    units and rate. Native/ezc3d readers, filters and LCS transforms preserve
    them. Edited C3D export retains them and uses the source C3D as a template
    to preserve unedited vendor/force-platform parameter groups.
  - `project_io.py` implements schema-1 `.vaila`: open ZIP + UTF-8 JSON, SHA-256
    member integrity, source provenance, no pickle/code/encryption/DRM.
  - GUI and direct `mkvis3d gui work.vaila` save/reopen current/raw trial,
    analog/force data, FPS, LCS, filter/display state, distance analyses,
    arbitrary JSON/CSV attachments, and source file.
  - Marker-defined orientation analysis outputs rotation matrices, scalar-first
    wxyz quaternions, all six Tait-Bryan sequences and gimbal-lock margins.
    Dynamics JSON can run through the GUI and its SI CSV is persisted.
  - Public specification: `docs/vaila-format.md`.
- **What Worked:**
  - Real `pilot0102_squat03.c3d` round-trip preserved all 24 analog channels,
    labels, units, samples and `FORCE_PLATFORM:CORNERS`.
  - Browser smoke verified FPS edit, orientation analysis, CoM, edited C3D and
    `.vaila` save/reopen with 71 markers and saved analyses.
  - `uv run pytest -q`: 218 passed in 48.40s; focused persistence/analysis
    suite: 36 passed.
  - `uv run ruff check .`, `uv run ty check openbiomech tests`, JavaScript
    syntax and `git diff --check` passed.
- **Failed Approaches:** A server test initially used arbitrary bytes as a C3D
  source template; template-preserving export correctly rejected it. Replaced
  with a valid generated C3D and pinned the behavior.
- **Open Questions & Next Steps:** Schema migrations must increment
  `SCHEMA_VERSION` and retain schema-1 reading compatibility. Unknown analysis
  keys are intentionally preserved for future biomechanical modules.
