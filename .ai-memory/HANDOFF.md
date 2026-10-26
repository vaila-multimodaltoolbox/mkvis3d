# Session Handoff: Resizable left sidebar
- **Status:** Completed (not committed)
- **Current State:** Left sidebar width is mouse-resizable via `#sidebar-splitter` (`.window-splitter-v`) between `#sidebar` and `#sidebar-toggle-rail`. Width driven by `--sidebar-width` on `#app-container` (default 280px, clamp 180–480 and container−320). Persisted in `localStorage` key `mkvis3d_sidebar_width`; splitter hidden when sidebar collapsed. Double-click resets to 280px. In-app manual bullet updated.
- **What Worked:** Mirrored existing `initHorizontalSplitter` / `initVerticalSplitter` pointer-capture pattern; device preference (not session/project) matching `mkvis3d_sidebar_visible`.
- **Failed Approaches:** none
- **Open Questions & Next Steps:** User can smoke-check in GUI (drag, reload persist, collapse, dblclick reset). Prior v0.0.3 docs/GUI hardening still uncommitted alongside this change.
