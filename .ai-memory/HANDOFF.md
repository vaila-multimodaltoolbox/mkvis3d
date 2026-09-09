# Session Handoff: Manual Coordinates Virtual Points & Vector Dot Product Angles

- **Status:** Completed
- **Current State:**
  - Implemented manual numerical coordinate virtual point creation ($X, Y, Z$) and vector spatial angle measurement via dot product in `openbiomech`.
  - **Features Delivered:**
    1. **Manual Coordinate Point Creation (`openbiomech/kinematic_analysis.py`, `openbiomech/viewer.html`, `openbiomech/viewer.js`):**
       - Mode switcher in `#modal-kinematics` Tab 1: `[📐 NumPy Formula]` and `[📍 Manual Coordinates (X, Y, Z)]`.
       - Manual 3D coordinate inputs ($X, Y, Z$ in meters) with step controls, `[📋 Copy from Active Marker @ Frame]`, and `Reset (0, 0, 0)`.
       - Virtual points table displays badge `📍 Manual [X, Y, Z] m` and provides Python export script preserving fixed coordinate arrays (`np.tile(np.array([X, Y, Z]), (len(trial.xyz), 1))`).
       - Backend `evaluate_virtual_point_expression` supports numeric list/array expressions `[x, y, z]`.
    2. **Vector Angle Measurement via Dot Product (`openbiomech/kinematic_analysis.py`, `openbiomech/viewer.html`, `openbiomech/viewer.js`):**
       - Exact mathematical formula:
         $$\mathbf{u} \cdot \mathbf{v} = \|\mathbf{u}\| \|\mathbf{v}\| \cos(\theta) \implies \theta = \arccos\left(\text{clamp}\left(\frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\| \|\mathbf{v}\|}, -1.0, 1.0\right)\right) \times \frac{180^\circ}{\pi}$$
       - Clamping strictly enforced to prevent `NaN` from floating point overshoot beyond $[-1.0, 1.0]$.
       - Python functions: `compute_vector_dot_product_angle(u, v, degrees=True)`, `compute_marker_angle(trial, a, b, c, degrees=True)`, `compute_two_vector_angle(trial, v1_a, v1_b, v2_c, v2_d, degrees=True)`.
       - Left Sidebar Panel: "ANGLE (DOT PRODUCT)" with 3-marker (vertex $\mathbf{u}=\mathbf{A}-\mathbf{B}, \mathbf{v}=\mathbf{C}-\mathbf{B}$) and 4-marker ($\mathbf{u}=\mathbf{B}-\mathbf{A}, \mathbf{v}=\mathbf{D}-\mathbf{C}$) modes.
       - Live numerical display: angle in degrees, $\mathbf{u}\cdot\mathbf{v}$, $\|\mathbf{u}\|$, $\|\mathbf{v}\|$, and `[📈 Plot Angle Curve on Timeline]` button.
       - 3D Viewport Visualization: colored vector lines (Cyan `#0284c7`, Amber `#d97706`), vertex highlight ring, circular arc, and billboard text label (`θ = XX.X°`).
       - Timeline multi-plot integration: `<option value="angle-dot-product">Angle (Dot Product °)</option>` on Plot 1 and Plot 2 with real-time curve rendering and NaN gap shading.
       - Longitudinal Axes Included Angle card added to Tab 3 of `#modal-kinematics` calculating $\arccos(\mathbf{e}_{z1} \cdot \mathbf{e}_{z2}) \times 180^\circ / \pi$.
    3. **Documentation:**
       - Updated Chapter 5 (3D Distance & Vector Angle Measurement) and Chapter 8 (Virtual Points & Secondary Landmark Creator) across `openbiomech/viewer.html` (`#modal-manual`), `docs/manual.html`, and `docs/MANUAL.md`.
  - **Standalone Linux Binary Rebuilt:** Updated `dist/mkvis3d` via `scripts/build_app.py`.
  - **Verification:**
    - Test suite: 232 passed, 3 deselected in 19.44s (`uv run pytest -m "not browser"`).
    - Ruff check & format: 0 errors across all 86 files (`uv run ruff check . && uv run ruff format --check .`).
    - Chrome CDP E2E tests: verified angle readout (`55.74°`), 4pt mode switch (`49.42°`), Plot 1 curve generation, manual coordinate virtual point creation, and Tab 3 longitudinal axes angle (`124.92°`).
    - Visual screenshots verified: `outputs/screenshot_angle_sidebar_plot.png` and `outputs/screenshot_manual_point_kinematics.png`.

- **What Worked:**
  - Clamping the dot product quotient prior to $\arccos$ ensures robust numerical stability across degenerate, near-parallel, and anti-parallel configurations in both Python backend and JS client.
  - Exposing `window.trial = data;` ensures smooth integration with external automation, CDP tests, and browser inspector workflows.

- **Failed Approaches:**
  - N/A.

- **Open Questions & Next Steps:**
  - All requested features, tests, builds, and documentation are complete.
