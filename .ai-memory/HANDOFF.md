# Session Handoff: User Manual & Biomechanics Theory Guide (Kwon3D & Visual3D Parity)

- **Status:** Completed
- **Current State:**
  - Implemented comprehensive User Manual and Biomechanics Theory Guide with Kwon3D parity (`http://www.kwon3d.com/theory/prac.html`) and Visual3D documentation depth.
  - **Deliverables:**
    1. **`docs/MANUAL.md`:** 12 comprehensive chapters (30+ KB) covering architecture, coordinate systems ($s_g, s_1, s_2$), Gram-Schmidt orthonormalization proofs, relative rotation matrix $MR = s_g s_1^T s_2 s_g^T$, Tait-Bryan Cardan/Euler decomposition (6 sequences), scalar-first quaternions, NumPy virtual points, Butterworth filtering, PCHIP gap interpolation, de Leva (1996) CoM, force plate kinetics (Types 1–5), multi-window navigation, Kwon3D parity cross-reference, practical tutorials, and keyboard shortcuts.
    2. **`docs/manual.html`:** Standalone, responsive, offline-ready HTML manual with dark/light theme, live search filter, sidebar TOC, math block styling, and print/PDF CSS.
    3. **In-App Modal (`#modal-manual`):** Integrated directly into `openbiomech/viewer.html` and `openbiomech/viewer.js`. Features live chapter filtering (`#manual-modal-search-input`), sidebar navigation TOC, popout/print button (`#btn-manual-popout`), and full keyboard navigation (`F1` / `Esc`).
    4. **GUI Access Points:**
       - Top Navbar: `[📖 Manual & Theory]` (`#btn-open-manual`)
       - Help Menu: `📖 User Manual & Biomechanics Guide... (F1)` (`#action-help-manual`)
       - Help Menu: `📐 Kwon3D Theory & Biomechanics...` (`#action-help-theory`)
       - Quick Shortcuts table updated with `F1 / ?`.
    5. **Documentation Hub & Readme:** Updated `README.md` and `docs/index.md` with links to the manual and theory guide.
  - **Standalone Linux Binary Rebuilt:** Executed `scripts/build_app.py` -> `dist/mkvis3d` packaging all updated HTML and JS assets.
  - **Verification:**
    - Full pytest suite: 227 passed (`uv run pytest -m "not browser"`).
    - Ruff check & formatting: 0 errors across 86 files (`uv run ruff check .` and `uv run ruff format --check .`).
    - Headless Chrome CDP E2E tests: verified modal opening via button, F1 shortcut toggle, Esc closing, TOC navigation, and live search filtering.
    - Screenshot captured and saved to `outputs/screenshot_manual_modal_live.png`.

- **What Worked:**
  - Embedding the manual modal directly into the HTML viewer while also offering a standalone `docs/manual.html` and Markdown `docs/MANUAL.md` provides 100% offline capability, github web browsing, and instant in-app assistance without network dependencies.

- **Open Questions & Next Steps:**
  - Ready for user feedback and further feature extensions.
