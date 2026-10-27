# Session Handoff: Multi-C3D skeleton + marker select/style
- **Status:** Completed (not committed)
- **Current State:** Opening several C3Ds now auto-guesses skeleton on file 0; clicking an overlay marker activates that layer and selects the point; marker color follows selection via `markerColorOverrides` (like size). Active-layer skeleton syncs to the Layers panel without clobbering on `load()`/`initSkeleton`.
- **What Worked:** `openOrLayerFiles(replaceFirst)` → `guessAndLoadSkeletonForTrial`; `pickMarkerAtScreen` + async `handleCanvasPointerUp`; per-label color overrides with session/layer stash; `syncActiveLayerSkeletonState` gated by `!switchingLayer`. Browser smoke: `uv run pytest tests/test_application.py::test_browser_smoke_automated` passed.
- **Failed Approaches:** Calling `syncActiveLayerSkeletonState` from `clearAllSkeletons` wiped the target layer template during `activateLayer`→`load`→`initSkeleton` before restore.
- **Open Questions & Next Steps:** User smoke-check in GUI (multi-select C3Ds → click each cloud → size/color/Load Skeleton). Prior uncommitted work (resizable sidebar, v0.0.3 docs) still uncommitted alongside this.
