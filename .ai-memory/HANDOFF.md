# Session Handoff: Release rp14set26 — awaiting auth/CI evidence

- **Status:** In-Progress
- **Current State:**
  - Commit `348c017` + tag `rp14set26` on `origin` (verified via `git ls-remote`).
  - Local Linux binary built: `dist/mkvis3d-linux-x86_64` (~79 MB).
  - GitHub Release assets not yet verified: `gh` unauthenticated; unauthenticated API/HTML scrape shows private-repo 404.
  - Device login pending: code `3948-64FC` → https://github.com/login/device (process still waiting).
- **What Worked:** Commit/push/tag/local build.
- **Failed Approaches:** Cookie scrape without session; API without token.
- **Open Questions & Next Steps:** User finishes Actions jobs and/or authorizes `gh`; then verify `gh release view rp14set26` lists Linux/Windows/macOS assets and mark goal complete.
