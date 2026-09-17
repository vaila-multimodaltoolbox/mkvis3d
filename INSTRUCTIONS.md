# mkvis3d (OpenBiomech) — Operational & Developer Guide

*Version: 0.4.3 | Updated: 17 September 2026*
*Main Entrypoint: `mkvis3d.py` | Standalone Package: `openbiomech`*

---

## 1. Quick Start

### Running the Application

```bash
# 1. Interactive 3D Web Viewer (Default Browser)
python mkvis3d.py
./mkvis3d_launcher.sh

# 2. Open a Motion File Directly (C3D, CSV, or .3d)
python mkvis3d.py data/rec3d_sample_m.c3d

# 3. Synchronized Multi-Camera Video Playback
python mkvis3d.py gui trial.c3d --video cam1.mp4 cam2.mp4

# 4. Generate Standalone Offline HTML Viewer
python mkvis3d.py view trial.c3d --output trial_viewer.html

# 5. Laboratory Coordinate System (LCS) Alignment
python mkvis3d.py lcs trial.c3d --ap +Z --axial +Y --output aligned.c3d

# 6. Gap Interpolation and Butterworth Low-Pass Filter
python mkvis3d.py filter trial.c3d --cutoff 6.0 --interp linear --output filtered.c3d
```

On Windows, double-click `mkvis3d.bat` or run:
```powershell
python mkvis3d.py
```

---

## 2. Integration with vailá Ecosystem

`mkvis3d` operates in tandem with `vaila` (Multimodal Biomechanics Toolbox):

1. **Reconstructed 3D Marker Sets**:
   - `vaila/rec3d.py` and `vaila/rec3d_one_dlt3d.py` output standard `*_m.c3d` (meters) and wide CSVs (`frame, p0_x, p0_y, ...`).
   - Load them directly into `mkvis3d` via drag-and-drop or command line.

2. **SAM 3D Body (DINOv3) Keypoints**:
   - Monocular 3D body pose estimation from `vaila/sam3dinov3.py` outputs 70 MHR keypoints.
   - Choose `SAM3+DINOv3 MHR-70 (70)` in the viewer dropdown for lateralized color coding:
     - Left side: Green (`#00ff00`)
     - Right side: Orange (`#ff8000`)
     - Midline: Light Blue (`#3399ff`)

3. **Soccer Pitch & 3D Goal Geometry**:
   - For stadium and sports field calibration, load `data/soccerfield_kiki_custom.c3d` or `vaila/models/soccerfield_kiki.csv`.
   - Choose `Soccer Field Kiki (49)` in the viewer dropdown to render pitch lines, 3D goal posts, crossbars, net depth ground points, corner flags ($z = 1.5$ m), center circle, and penalty arcs.
   - Center circle and penalty arcs ("meia-lua") are **procedural** (not skeleton bones). Geometry follows FIFA Law 1 / vailá `drawsportsfields.penalty_arc_geometry`: radius from stored arc intersections or the centre-circle Y span (fallback 9.15 m); arc clipped to the penalty-area line and drawn only outside the box toward midfield.

---

## 3. Skeleton Templates & Dual-Index Support

`skeleton_templates/` hosts 14 standardized skeleton connection maps:
- `mediapipe_pose33.json` (33 kp)
- `yolo_coco17.json` (17 kp)
- `openpose_body25.json` (25 kp)
- `halpe26.json` (26 kp)
- `fifa_body15.json` (15 kp)
- `sam3dinov3_mhr70.json` (70 kp)
- `sapiens2_goliath308.json` (308 kp)
- `mediapipe_hand21.json` (21 kp)
- `mediapipe_hands42.json` (42 kp)
- `mediapipe_holistic75.json` (75 kp)
- `coco_wholebody133.json` (133 kp)
- `soccerfield_pitch32.json` (32 kp)
- `soccerfield_calib29.json` (29 kp)
- `soccerfield_kiki49.json` (49 kp)

### Dual-Index Engine
The viewer (`openbiomech/viewer.js`) and Python backend (`openbiomech/skeleton.py`) transparently detect:
- **0-based indexing** (`p0..p(N-1)`): Used by vailá wide CSV exports (`p0_x, p0_y, ...`).
- **1-based indexing** (`p1..pN`): Used by legacy templates and C3D marker indices.
- **Semantic names**: Labels like `Nose`, `Left_Shoulder` resolve case-insensitively with hyphen/underscore normalization.

---

## 4. Keyboard Shortcuts

- `Space`: Play / Pause animation playback
- `←` / `→`: Step one frame backward / forward
- `Home` / `End`: Jump to start / end frame
- `+` / `-`: Increase / decrease marker sphere size
- `C`: Toggle trajectory trail lines
- `F`: Focus / center 3D camera
- `Left Click + Drag`: Orbit 3D perspective
- `Right Click + Drag`: Pan camera
- `Scroll Wheel`: Zoom
- Double-click Splitter: Reset bottom plot panel height to default (170 px)

---

## 5. Automated Tests

```bash
cd /home/preto/data/mkvis3d
.venv/bin/pytest tests/test_skeleton_templates.py -v
.venv/bin/pytest tests/test_application.py tests/test_cli.py tests/test_blender_io.py -v
```
