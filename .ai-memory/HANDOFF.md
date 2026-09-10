# Session Handoff: CSV Trajectory Matrix Import, In-Place Replacement & Frame Blanking

- **Status:** Completed
- **Current State:**
  - Implemented external CSV coordinate matrix loading (rows=frames, cols=X,Y,Z), in-place marker trajectory replacement, frame gap blanking/cleaning (single frame, sequence range, and CSV frame list file), individual marker CSV export, and 1-click non-destructive raw data restoration in `mkvis3d` / `openbiomech`.
  - **Features Delivered:**
    1. **Python Backend Trajectory Editing (`openbiomech/kinematic_analysis.py`):**
       - `load_marker_trajectory_csv(source, expected_frames=None)`: parses 3-column (`X, Y, Z`), 4-column (`frame/time, X, Y, Z`), and 5-column (`frame, time, X, Y, Z`) CSV/text matrices with automatic delimiter detection (`,`, `;`, `\t`, whitespace) and header detection (`x`, `y`, `z`, `frame`, `time`). Handles empty cells and `NaN`/`null` as `np.nan` coordinate gaps. Supports frame padding and truncation.
       - `parse_frame_list_csv(source)`: parses frame numbers from CSV/text containing numbers, commas, spaces, newlines, or range intervals (e.g. `10-25`).
       - `export_marker_trajectory_csv(trial, marker_name, filepath=None)`: exports single marker trajectory to RFC 4180 CSV with columns `frame,time_s,x,y,z`.
       - `replace_marker_trajectory(trial, marker_name, new_xyz)`: updates `trial.xyz` and `trial.residuals` in-place.
       - `add_marker_trajectory(trial, marker_name, new_xyz, residual=0.0)`: appends new marker/point trajectory.
       - `blank_marker_frames(trial, marker_name, frames=None, frame_range=None, csv_frames_source=None)`: blanks target frame coordinates to `np.nan`.
    2. **Python Server API (`openbiomech/viewer.py`):**
       - Registered and validated POST endpoints: `/api/analyze/import_trajectory_csv`, `/api/analyze/export_trajectory_csv`, and `/api/analyze/blank_frames`.
    3. **Frontend UI & Workflows (`openbiomech/viewer.html`, `openbiomech/viewer.js`):**
       - **Top Menu (`File ▾`):**
         - Added `Export Active Marker (CSV)...`
         - Added `Import / Replace Marker Trajectory (CSV)...`
       - **Top Menu (`Kinematics ▾`):**
         - Added `✂️ Clean / Blank Marker Frames (NaN Gaps)...` (opens directly to Tab 1 cleaning controls).
       - **Sidebar Action Bar (Under Active Marker):**
         - `[📥 Export CSV]`: One-click download of selected marker trajectory to CSV.
         - `[✂ Blank Frame]`: Sets $(X, Y, Z)$ of selected marker to `null` (`NaN` gap) at the current paused playback frame.
         - `[⚙️]`: Opens Kinematics Modal Tab 1.
       - **Kinematics Modal Tab 1 Mode Switcher:**
         - Added 3rd mode button: `[📊 CSV Trajectory]`.
         - Container C provides destination options:
           - Radio: `Create as New Point` (with point label input) vs `↻ Replace Existing Marker` (with target marker selector).
           - File selector `#vp-csv-file-input` with automatic delimiter detection and coordinate validation.
           - Preview badge `#vp-csv-status-badge`.
       - **Kinematics Modal Tab 1 Fieldset (`✂️ Marker Trajectory Cleaning & Gap Blanking`):**
         - Marker selector with dynamic sync to active marker.
         - Scope radios: `Current frame (f = X)`, `Sequence range (From ... To ...)`, `CSV frame list file`, `All frames`.
         - `[❌ Blank Selected Frames]`: Blanks coordinates in real-time, immediately clearing 3D marker, timeline curves, and kinematics.
         - `[↩ Restore Marker Raw Data]`: Non-destructive 1-click restore to original raw coordinates from session memory.
         - `[📥 Export Marker (.csv)]`: Standalone marker export.
         - Defined points list: download icon `📥` per point row and `[📥 Export All Trajectories (.csv)]` bottom pipeline bar.
    4. **Documentation:**
       - Updated Section 4 in `docs/MANUAL.md` with complete documentation of CSV trajectory matrices, in-place replacement, gap blanking methods, and the external roundtrip workflow.
       - Updated Chapter 8 in `docs/manual.html` and `#modal-manual` in `openbiomech/viewer.html`.
    5. **Artifacts & Distribution:**
       - Re-generated standalone HTML viewer: `outputs/rec3d_viewer.html`.
       - Rebuilt Linux binary: `dist/mkvis3d`.
  - **Verification:**
    - Python unit tests (`tests/test_marker_trajectory_editing.py`): 8 passed in 0.60s.
    - Full test suite (`uv run pytest -m "not browser"`): 239 passed, 4 deselected in 17.17s.
    - Live sync test (`uv run pytest tests/test_video_sync_live.py`): 1 passed in 3.84s.
    - Linting & Formatting: `uv run ruff check .` passed with zero warnings; `uv run ruff format --check .` passed on all 87 files.
    - End-to-end browser automation (`scratch/run_point_csv_test.sh`): verified sidebar action buttons, current frame blanking, sequence range blanking, 1-click restore, CSV trajectory new point creation, and in-place marker replacement. Screenshot saved at `outputs/screenshot_point_csv_cleaning.png`.
    - Binary verified: `./dist/mkvis3d --help` returns zero exit code.

- **What Worked:**
  - Synchronizing `rawLoadedXYZ` alongside `trial.xyz` ensures that filtering or LCS transformations do not overwrite newly replaced trajectories or lose track of raw data needed for `[↩ Restore Marker Raw Data]`.
  - Flexible matrix parsing (supporting 3, 4, or 5 columns and various delimiters) accommodates outputs from Qualisys, Vicon, OptiTrack, OpenSim, Python/NumPy, and MATLAB.

- **Failed Approaches:**
  - N/A.

- **Git Status Reminder:**
  - In accordance with user rules, NO `git add`, `git commit`, or `git push` commands were executed. Version control operations are reserved exclusively for the user.
