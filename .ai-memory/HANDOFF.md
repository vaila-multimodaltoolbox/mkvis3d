# Session Handoff: Prominent Kinematics Buttons in Menubar, 3D Viewport Header, Plot 1, & Sidebar

- **Status:** Completed
- **Current State:**
  - Placed prominent, unmissable Kinematics access points across the GUI:
    1. **Top Menubar:** Added top-level menu **`📐 Kinematics ▾`** directly between `Windows ▾` and `Options ▾`. Also added entries in `Windows ▾`, `Options ▾`, `View ▾`, and `File ▾` (export).
    2. **3D Viewport Window Header:** Added prominent button **`[📐 Bases & Kinematics (s1, s2, sg)]`** directly in `#panel-3d .pane-tools` next to `↻ Refresh 3D` and `⧉`.
    3. **Plot 1 Window Header:** Added button **`[📐 Kinematics]`** directly beside the plot series mode dropdown.
    4. **Left Sidebar:** Moved the `Segment Kinematics` section up to the TOP of the sidebar right below `Point Selection` (above Marker Appearance, Skeleton, etc.), making it immediately visible on any screen resolution without scrolling.
    5. **Keyboard Shortcut:** Added **`Alt + K`** to toggle the Kinematics modal open/closed from anywhere.
  - Standalone Linux binary recompiled via `scripts/build_app.py` -> `dist/mkvis3d` (76 MB standalone onefile executable).
  - All 227 pytest tests passed (`uv run pytest -m "not browser"`), `uv run ruff check .` passed with 0 errors, `uv run ruff format --check .` passed, automated headless Chrome CDP test suite (`tests/browser_smoke.mjs` and `scratch/test_gui_buttons.mjs`) verified all interactions and captured visual screenshots (`screenshot_gui_all_buttons_visible.png`, `screenshot_gui_kinematics_buttons.png`).
  - Changes committed and pushed to `main` (`c5c683d` and `1fcfcb1`).

- **What Worked:**
  - Multi-location exposure (Top Menubar + 3D Viewport header + Plot 1 header + Sidebar top + Alt+K shortcut) ensures the user can find and access the Segment Bases ($s_1, s_2, s_g$) & Relative Kinematics window from whatever area of the application they are looking at.

- **Failed Approaches:**
  - Placing the kinematics button only at the bottom of the long sidebar meant it was pushed off-screen / below the scroll fold on standard monitor heights, and wasn't discoverable in the menus or viewport windows.

- **Open Questions & Next Steps:**
  - None; all user requirements fulfilled and verified.
