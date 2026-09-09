# Session Handoff: mkvis3d Complete User Manual & Biomechanics Guide

- **Status:** Completed
- **Current State:**
  - Implemented comprehensive User Manual and Biomechanics Guide covering 100% of `mkvis3d` features, tools, algorithms, and workflows, modeled after the depth of classical literature (`kwon3d.com` and Winter's textbook) without adopting external branding.
  - **Deliverables:**
    1. **`openbiomech/viewer.html` & `openbiomech/viewer.js` (`#modal-manual`):**
       - 14 complete chapters embedded directly inside the GUI modal with clean Unicode typography (zero raw LaTeX artifacts).
       - Live search input dynamically filtering chapters and sidebar TOC items.
       - Popout / Print button (`#btn-manual-popout`) allowing detached window viewing and clean PDF printing.
       - Renamed Help menu item to **`📐 Biomechanics Theory & Mathematics...`** (`#action-help-theory`) navigating straight to Chapter 6 (Coordinate Systems & Bases).
       - Top navbar button **`[📖 Manual & Theory]`** (`#btn-open-manual`) and shortcut **`F1`**.
    2. **`docs/manual.html`:** Standalone, responsive, offline single-file HTML manual with dark/light theme toggle, live search, and print/PDF CSS.
    3. **`docs/MANUAL.md`:** 14 detailed chapters for GitHub repository browsing.
    4. **Coverage:**
       - Chapter 1: System Overview & Architecture
       - Chapter 2: Data Formats & Biomechanical I/O (C3D, CSV, .3d, .vaila, BVH, Blender)
       - Chapter 3: 3D Viewport & Scene Navigation (Orbit, Pan, Zoom, ↻ Compositor Refresh, ⧉ Popouts)
       - Chapter 4: Interactive Timeline & Multi-Plot Analysis (Scrubber, X/Y/Z isolation, NaN gap bands, 1-click gap fill)
       - Chapter 5: Point Selection & 3D Distance Measurement (Euclidean metrics, live curve, stats)
       - Chapter 6: Coordinate Systems & Orthonormal Bases (sg, s1, s2, Gram-Schmidt proofs)
       - Chapter 7: Relative Joint Kinematics (MR = sg s1^T s2 sg^T, 6 Euler sequences, Quaternions)
       - Chapter 8: Virtual Points & Secondary Landmark Creator (NumPy formulas, script export)
       - Chapter 9: Signal Conditioning: Filtering & Gap Interpolation (Hampel, PCHIP, Butterworth 4th zero-phase)
       - Chapter 10: Anthropometry & Whole-Body Center of Mass (de Leva 1996 16-segment model)
       - Chapter 11: Force Platforms, Ground Reaction Forces & Kinetics (Types 1-5, COP, Newton-Euler inverse dynamics)
       - Chapter 12: Video Synchronization & Multi-Window Desktop (Sync offset, popout monitors)
       - Chapter 13: Command-Line Interface (CLI) Complete Reference (all 10 commands)
       - Chapter 14: Practical Tutorials, Standards & Shortcuts (Gait, Squat, CMJ, shortcut table)
  - **Standalone Linux Binary Rebuilt:** Updated `dist/mkvis3d` via `scripts/build_app.py`.
  - **Verification:**
    - Full pytest suite: 227 passed (`uv run pytest -m "not browser"`).
    - Ruff check & format: 0 errors across all 86 files.
    - Chrome CDP E2E tests: verified modal opening, chapter count (14), TOC navigation, search filtering, F1 shortcut, Esc close, popout button.
    - Screenshot captured: `outputs/screenshot_manual_modal_live.png`.

- **What Worked:**
  - Standardizing mathematical equations with clean Unicode characters (`·`, `×`, `√`, `||e||`) ensures crisp, legible rendering across all environments without external math renderers.

- **Open Questions & Next Steps:**
  - Goal complete and ready for user inspection.
