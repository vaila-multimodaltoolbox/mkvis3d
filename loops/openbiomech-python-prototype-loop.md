---
name: openbiomech-python-prototype
category: Vailá
trigger: manual
verification-level: 1
theory-base: arXiv:2607.00038
---

# OpenBiomech Python Prototype Loop

## Description
Build `openbiomech/` module-by-module in Python (de-risking phase before the
Rust rewrite specified in `README.md`), one function/module per iteration,
gated on deterministic tests, ending in a human decision gate on whether to
port to Rust.

## Use When
Use for: implementing or extending anything under `openbiomech/c3d_io/`,
`openbiomech/biomech_math/`, `openbiomech/model/`, `openbiomech/inverse_dynamics/`.
Do not use for: `viewer-core`/`gui-app`/`pipeline-cli` (not started, no spec
yet), any change to `README.md` (frozen — long-term Rust reference, never
edited by this loop), or actually writing Rust/`Cargo.toml` (Phase 5 is a
decision gate only, not implementation).

## Inputs
1. `phase` — which of the 5 phases below to work in this run. Default: the
   lowest-numbered phase not yet at `done` in the state file.
2. `target` — optional specific module/function within that phase (e.g.
   `legacy_binary.read_c3d`). Default: worst/highest-priority unresolved item
   in that phase's backlog (see Iteration step 3).

## Goal
Each README.md crate gets a working, tested Python module in `openbiomech/`
(see `CLAUDE.md`'s crate→module table), culminating in a human go/no-go
decision on the Rust port. Objectively verifiable per-phase (pytest green);
the final Rust-port decision is a human checkpoint, not an automated check.

## Verification (Governing Check)
- **True level:** 1 (deterministic) for phases 1–4; 5 (human checkpoint) for
  phase 5.
- **Check:** `uv run pytest tests/ -k <module> -v` for the module touched
  this iteration, then `uv run pytest -v` (full suite) before accepting.
  Phase 1 additionally requires `tests/test_c3d_io_golden.py` to pass with
  `legacy_binary.read_c3d` swapped in for `ezc3d_reader.read_c3d` in a
  dedicated comparison test (not yet written — first iteration of phase 1
  writes it) at the same `1e-3` coordinate tolerance already established.
- **Evidence:** raw stdout of both pytest invocations, plus
  `uv run ruff check . && uv run ty check` output, recorded verbatim in the
  state file for that iteration.
- **Completion criterion:** pytest exit code 0 for the targeted `-k` filter
  AND the full suite, ruff/ty clean (or pre-existing documented exception —
  currently none after the `README.md` ruff-format exclude was added to
  `pyproject.toml`), no regression vs. the previous iteration's passing test
  count.
- **Verifier protection:** the golden fixture (`data/*`, symlinked at
  `tests/fixtures`) is read-only — no iteration may edit or regenerate it.
  `ezc3d_reader.py` (the oracle for phase 1) may not be modified to make
  `legacy_binary.py` agree with it; only `legacy_binary.py` may change.
  Existing passing tests may not be deleted, weakened (loosened tolerance,
  removed assertion), or skipped to reach green.
- **Scientific validity:** units are metres/mm as already present in the
  fixture (unchanged by this loop), coordinate frame is whatever the source
  `rec3d` DLT reconstruction used (not re-derived here), sample rate is fixed
  at 100 Hz per the fixture header, marker identity is `p1..p70` by column
  name (not position) per `csv_io._point_numbers_from_columns`. Phase 4's
  force-plate work has no fixture yet (`data/` carries 0 analog channels) —
  its first iteration must build or source a synthetic force-plate fixture
  with a hand-computed expected COP before any COP/Newton-Euler code lands.

## Trigger
Manual: user or a supervising agent runs one iteration by invoking this
document explicitly (e.g. via `preto-loop`'s own execution convention or a
fresh-context runner). No scheduled/event trigger — this is deliberate,
multi-session module-by-module work, not a CI job. Re-entrant: state file
(`loops/state/openbiomech-python-prototype.json`) is the single source of
"what phase/target is next," so re-running this document with no `phase`/
`target` input is always safe and picks up where the last run left off.

## Iteration
0. On the first iteration ever, create
   `loops/state/openbiomech-python-prototype.json` with all 5 phases at
   status `pending` except phase 1 at `active`; validate `phase`/`target`
   inputs against that state.
1. Load this document and the state file; confirm turn budget remaining and
   that no pending human approval is outstanding (git commit, new dependency).
2. Snapshot: `git status --short` (must be clean or contain only this loop's
   own prior uncommitted work — never someone else's uncommitted edits), then
   run the full governing check to record the current baseline pass count.
3. Within the active phase's backlog (see per-phase notes below), rank
   unresolved targets worst-first and select one:
   - Phase 1 backlog: 512-byte header parse → processor-flag (VAX/Intel/MIPS)
     dispatch → POINT/ANALOG parameter-group parse → VAX-float-to-IEEE
     conversion (only needed if a real VAX-flagged file ever appears in
     `data/`; this fixture is Intel) → frame/point data extraction → the
     dedicated `legacy_binary` vs. `ezc3d_reader` comparison test.
   - Phase 2 backlog: quaternion construction from `kabsch`'s `R` → SLERP →
     Euler/Cardan sequence conversion → GCVSPL smoothing spline → additional
     synthetic edge cases (near-degenerate rotations, single-marker input).
   - Phase 3 backlog: landmark/segment definitions → ISB JCS per joint
     (starting with knee/ankle, per README's worked example if present) →
     BSP (de Leva or similar table) → gait-event detection.
   - Phase 4 backlog: synthetic force-plate fixture first, then COP for
     platform types 1–5, then recursive Newton-Euler per segment.
   - Phase 5: not an implementation backlog — see Terminal States.
4. Implement exactly one module/function change (new file or function, not a
   sweeping refactor) for the selected target, citing its `vailá` source in
   the docstring when one exists (per `CLAUDE.md`'s reuse table); write its
   deterministic test in the same iteration.
5. Run the governing check; capture raw output.
6. Accept the change only if the full suite passes with no regression;
   otherwise revert via `git checkout -- <files>` / `git clean` for untracked
   new files from this iteration only (nothing from prior iterations).
7. Update the state file atomically (write to a temp file, then rename):
   baseline pass count, this iteration's target/result/evidence-summary,
   phase status (`active`/`done` when its backlog is empty and its tests are
   green), cost so far, any curated lesson.
8. Evaluate terminal states below; otherwise begin the next iteration.

## Terminal States
- **success:** phases 1–4 all `done` (every backlog item implemented, full
  `uv run pytest -v` green, `ruff check`/`ty check` clean) AND phase 5's
  human decision has been recorded in the state file (`rust_port_decision:
  "go"|"no-go"|"defer"`).
- **no-op:** invoked with an already-`done` phase and no other phase ready to
  start (e.g. phase 2 requested but phase 1 not yet `done`) — report and stop
  without changes.
- **no-progress/stalled:** 2 consecutive iterations in the same phase end
  with the golden/deterministic test for that phase's target still failing
  (or, for phase 1 specifically, no improvement in `legacy_binary` vs.
  `ezc3d_reader` agreement) — stop and report the specific failing assertion,
  do not attempt a 3rd iteration on the same target.
- **blocked:** the target requires a decision not already fixed in this
  document or `CLAUDE.md`/`README.md` (e.g. which BSP table, which JCS
  convention variant, whether to accept a new dependency) — stop, name the
  exact question, do not guess.
- **exhausted:** turn/token/cost ceiling (see Guardrails) reached before a
  phase's backlog is empty — stop, leave state file consistent for resume.

Errors, missing evidence, and budget exhaustion are never success.

## Guardrails
- **Maximum allocation:** 40 turns per invocation of this loop (one phase's
  worth of iterations, roughly); no currency cost (local compute only, no
  paid API calls beyond the agent's own).
- **Human approval required:** any `git commit`/`git push`; any new
  dependency beyond `numpy`, `scipy`, `pandas`, `ezc3d`, `pytest`, `ruff`,
  `ty` already in `pyproject.toml`; deleting/modifying `data/*` or
  `README.md`; the phase 5 Rust-port go/no-go itself.
- **Isolation and credentials:** local filesystem only, no network access
  needed for any phase, no credentials in scope.
- **Protected verifier:** `tests/fixtures` (symlink to `data/`),
  `ezc3d_reader.py` (phase 1's oracle), and any already-passing test's
  assertions/tolerances are off-limits for modification by this loop.
- **Rollback:** `git checkout -- <new/modified files>` and `git clean -fd`
  scoped to files touched in the current iteration only (repo has no commits
  yet during early phases, so "revert" may mean deleting the file created
  this iteration — never delete a file from a prior accepted iteration).

## State Memory
- **Path:** `loops/state/openbiomech-python-prototype.json`.
- **Persist:** `phases` (status per phase 1–5), `baseline_pass_count`,
  `iterations` (list of `{phase, target, result, evidence_summary,
  timestamp}`), `accepted_changes`, `rejected_attempts`, `curated_lessons`,
  `cost_turns_used`, `rust_port_decision`.
- **Recovery:** a fresh context reads this file first; if the last recorded
  iteration has no matching `result` (interrupted mid-write), re-run the
  governing check before trusting any in-progress iteration's claimed state
  — the temp-file-then-rename write pattern means a half-written iteration
  never becomes the live file, so recovery only needs to re-verify the last
  *complete* entry against current disk state (tests still pass?).

## Skills
- No named `vaila-*` skill applies directly (this is a new, separate repo);
  reuse is source-level (citing `vailá` files in docstrings per
  `CLAUDE.md`), not skill-level.
- `$test-writer`-equivalent judgment (write the deterministic test in the
  same iteration as the implementation, per Iteration step 4) — no dedicated
  skill invoked, done inline.

## Sub-Loops
None. Single flat loop across 5 sequential phases; phase boundaries are
state-file gates, not separate loop documents.

## Why It Works
One module/function per iteration (step 4) keeps each change attributable
and revertible (Rollback). The golden fixture (real `vailá` `rec3d` export,
already cross-validated CSV-vs-C3D in the scaffold's own tests) gives phase
1 a deterministic level-1 oracle instead of relying on Visual3D, which the
user does not have. Citing exact `vailá` source functions in docstrings
prevents silently reinventing already-tested math (Kabsch, Butterworth).
Explicit stalled/blocked states stop the loop from guessing its way past a
failing golden-fixture comparison or an unresolved spec ambiguity (e.g. BSP
table choice) instead of shipping a plausible-looking wrong answer. The
phase-5 human checkpoint keeps the Rust-or-not decision — the single most
expensive and hardest-to-reverse choice in this whole project — outside the
loop's own authority.

## How to Trigger
### Context-bound
Not applicable in this harness as a slash-command; invoke by having an agent
read this file and follow Iteration steps 0–8 directly, once per turn, in
the current session.

### Fresh-context / Ralph
External runner contract: each new session/context re-reads this document
in full plus `loops/state/openbiomech-python-prototype.json` before acting;
runs exactly one iteration (steps 1–8); stops on any Terminal State; never
treats "agent said it looks done" as `success` — only the recorded pytest
exit codes and phase statuses in the state file count.

## Health Metrics
- **Cost per accepted change:** `cost_turns_used / len(accepted_changes)`.
- **Phase completion:** count of phases at `done` out of 5.
- **Golden-fixture agreement (phase 1):** max `|legacy_binary - ezc3d|`
  coordinate difference, tracked per iteration until `< 1e-3` (matching the
  existing CSV-vs-C3D tolerance in `tests/test_c3d_io_golden.py`).
- **Regression count:** any iteration where the full-suite pass count drops
  vs. `baseline_pass_count` (should always be 0 — those iterations are
  rolled back per step 6).
