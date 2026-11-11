# Session Handoff: Release prep v0.0.4
- **Status:** Completed (not committed)
- **Current State:** Package bumped to **0.0.4** (`pyproject.toml`, `__init__.py` fallback, README, version test). MediaPipe-33 CoM + short `CoM` label shipped. LCS force-plate transform now builds a real `ForcePlatform` (was using invalid `rate_hz` kwargs).
- **What Worked:** Verification: `uv run pytest -q` → **325 passed, 3 skipped**; `uv run ruff check .` / `ruff format` clean; `uv run ty check` clean (blender_addon excluded).
- **Failed Approaches:** Browser smoke/cross-browser initially failed on stale `CenterOfMass_deLeva_male` expectation and `DEFAULT` vs `DEFAULT (THEME)` badge text — tests updated.
- **Open Questions & Next Steps:** User can commit/tag when ready. No commit/push performed by agent.
