# Session Handoff: README rewrite (vailá style) + docs/ help pages
- **Status:** Completed
- **Current State:**
  - `README.md` was a garbled, mislabeled artifact (a raw Python script + its
    stdout that *generates a CLAUDE.md*, wrapped in a stray ` ```python ` code
    fence) — not a real project README. Rewritten from scratch in the style of
    `/home/preto/data/vaila/README.md`: OS/install table, intro, relationship
    to vailá, current-status crate table, project tree, install/run/build/test
    sections, data fixture note, documentation links, citing, contribution,
    license (AGPLv3, matching `pyproject.toml`).
  - Created `docs/` with both Markdown and HTML help pages, as requested:
    `docs/index.{md,html}` (hub), `docs/cli.{md,html}` (full `mkvis3d` CLI
    reference derived from `openbiomech/cli.py`'s `build_parser()`),
    `docs/architecture.{md,html}` (the long-term Rust workspace + ISB/Kabsch/
    Butterworth/GCVSPL/force-plate/Newton-Euler math spec that used to live,
    badly formatted, inside `README.md`).
  - Updated `CLAUDE.md`'s Provenance section and the two `README.md §3.x`
    cross-references in Conventions to point at `docs/architecture.md`
    instead, since the target-architecture content moved out of `README.md`.
  - Updated `pyproject.toml`'s `[project].description` (same README.md →
    docs/architecture.md pointer fix).
  - Added an explicit "Relationship to _vailá_" section to `README.md` per
    the user's stated future-integration plan.
- **What Worked:**
  - Read `pyproject.toml`, `openbiomech/cli.py` (full `argparse` surface),
    `AGENTS.md`, `mkvis3d.spec`/`scripts/build_app.py`/`.github/workflows/
    build_executables.yml`, and the launcher scripts (`mkvis3d.bat`/
    `.command`/`_launcher.sh`) to keep the new README's install/build/CLI
    sections accurate to what actually exists (no fabricated install
    scripts, version banners, or citations).
  - No AGPL `LICENSE` file exists in the repo despite `pyproject.toml`
    declaring `AGPL-3.0-or-later` — README's License section links to the
    canonical license text rather than a repo-local `LICENSE` file that
    isn't there; flagged here rather than silently adding one.
- **Failed Approaches:** none.
- **Open Questions & Next Steps:**
  - Consider adding a `LICENSE` file (AGPL-3.0-or-later) at repo root — not
    added this session since it wasn't asked for and is a licensing decision
    worth a human nod.
  - `docs/cli.md`/`.html` should be re-checked whenever `openbiomech/cli.py`'s
    `build_parser()` gains/changes a subcommand or flag — it is hand-written,
    not generated from `argparse` help text.
