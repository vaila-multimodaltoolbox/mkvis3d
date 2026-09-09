# Session Handoff: Cartesian Bases (s1, s2, sg), Virtual Points Creator & Relative Kinematics

- **Status:** Completed
- **Current State:**
  - Removed orientation / Euler / Quaternion clutter from the left sidebar and replaced it with a single clean button: `📐 Segment Bases (s1, s2, sg) & Kinematics`.
  - Added dedicated floating modal window (`#modal-kinematics`) with 4 tabs:
    1. **Virtual Points Creator:** Allows users to define custom virtual landmarks using NumPy vector expressions (e.g. `(p['p1'] + p['p2']) / 2`, cross products, offsets). Multiple points can be added indefinitely with custom names and are immediately appended to `trial.labels` and `rawLoadedXYZ`.
    2. **Cartesian Bases ($s_1, s_2, s_g$):** Define two segment Cartesian bases ($s_1$ proximal, $s_2$ distal) and Global lab system ($s_g$) using 3 non-collinear points (Origin, Primary Axis, Plane point) and axis permutations.
    3. **Live Relative Kinematics:** Computes relative orientation using the exact user-specified formulation:
       $$MR_2 = s_g \cdot s_1^T$$
       $$MR = (MR_2 \cdot s_2) \cdot s_g^T = s_g \cdot s_1^T \cdot s_2 \cdot s_g^T$$
       Strictly enforces Gram-Schmidt orthonormalization: unit norm ($\|e\| = 1$, each versor divided component-by-component by its Euclidean norm), mutual perpendicularity ($90^\circ$), and right-handed parity ($\det = +1$).
       Displays real-time $3 \times 3$ $MR$ rotation matrix, Cardan/Euler angles across all 6 Tait-Bryan sequences (`zxy`, `xyz`, `zyx`, `yxz`, `xzy`, `yzx`), and scalar-first unit quaternions $(w, x, y, z)$.
       Scrubbing the timeline or playing the animation updates the live telemetry in real-time and renders 3D RGB triads directly at segment origins in the 3D viewport.
    4. **Export & Pipeline:** Allows 1-click export of kinematics matrices and Euler/Quaternion angles to CSV, and generates a standalone, reusable Python script pipeline (`.py`) containing the point definitions and orthonormal basis transformations.
  - Linux binary distribution built and verified via `scripts/build_app.py`: standalone single-file executable `dist/mkvis3d` (76MB, no Python required).
  - All 227 pytest tests passed (`uv run pytest -m "not browser"`), `uv run ruff check .` passed with 0 errors, `uv run ruff format --check .` passed, and automated headless Chrome CDP test suite (`tests/browser_smoke.mjs` and `scratch/test_kinematics_e2e.mjs`) verified all interactions.

- **What Worked:**
  1. **Strict Orthonormalization:** Gram-Schmidt projection followed by explicit vector normalization ensures $\|e_x\|=\|e_y\|=\|e_z\|=1.0$, $e_i \cdot e_j = 0$, and $\det = +1.0$ at every frame.
  2. **Dual Engine Architecture:** Standalone JavaScript engine powers the offline HTML viewer exports without server connectivity, while Python backend (`/api/analyze/kinematics_bases` and `/api/analyze/evaluate_point`) provides an oracle for GUI server mode and automated pytest regression tests.
  3. **Live Telemetry & 3D Triad Overlay:** RGB triad rendering (Red=X, Green=Y, Blue=Z) directly at segment origins provides immediate visual spatial orientation feedback during playback.
  4. **Dynamic Plot Integration:** Sending Euler angles directly to Plot 1 (`mode="kinematics-euler"`) seamlessly graphs flexion/extension, ab/adduction, and internal/external rotation curves across the motion timeline.

- **Failed Approaches:**
  - In `buildOrthonormalBasisJS`, declaring `const valid = [];` shadowed the outer point validity predicate `valid(p)`. Renamed the collection array to `validMask` to resolve the shadowing error.
  - Relying on default browser `<select>` option indices without explicit dataset flags caused select elements to initialize to index `0`. Handled via `sDefaults` map setting distinct default marker indices (0, 1, 2 for $s_1$; 3, 4, 5 for $s_2$).

- **Open Questions & Next Steps:**
  - Stage, commit, and push all verified changes to `main`.
