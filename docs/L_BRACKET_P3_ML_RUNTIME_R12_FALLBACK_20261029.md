# GeoField L-bracket P3 — existing ML automatic runtime fallback and status audit (2026-10-29)

## Scope frozen
Only the user's original L-bracket STEP and previously installed *optional* BrepMFR/R12 research features. No new CAD geometry families, no ML retraining, no private model checked into Git, no inference accuracy claim, no CAD/FEA/3D solver changes, no external paid DeepSeek calls.

## Confirmed source failure
Previously `launch_automatic_ml` correctly started `launch_automatic_r12` if **BrepMFR preflight was unavailable**. However when preflight said available, `execute_ml` ran its native worker, caught a worker exception, recorded `ML_JOBS[run_id].status='failed'` and exited **without the existing R12 fallback**. The automatic frontend `watchAutoMl` received `failed`, stopped, and never invoked `watchAutoR12`. This explains one concrete route by which a valid STEP CAD/FEA workflow can have no automatic research ML analysis even when the previously available local R12 worker is ready. It is **not proof** that this was the particular cause on the owner's installed Windows; that needs installed source/log inspection.

## Code fix
1. The failed original worker's `ML_JOBS` status and truncated exception message remain genuinely **failed**, and its existing `ml_failed` archival path is unchanged.
2. Only if this was the **registered current automatic** run (`automatic is True`, owner opted in, CAD complete/current, exact CAD SHA + run ID unchanged) **and** the still-owned disposable ML input STEP passes exact SHA verification, `execute_ml` calls the **existing** `launch_automatic_r12`. That routine performs its own R12 preflight, deduplication, verifies and creates a separate run-owned STEP copy and starts the pre-existing bridge. Nothing touches original STEP, FEA/FRD, SQLite or private BrepMFR checkpoint.
3. For a valid attempted fallback, current CAD's `auto_ml_status='r12_fallback'`. If the R12 model is missing, `auto_r12_status='unavailable'` and frontend immediately reports failure when it checks `/api/ml/r12/latest`; no fabricated research result. If fallback cannot even start, `auto_ml_status='failed'` with explicit R12 error.
4. Existing `GET /api/ml/latest/<uid>` still calls strict `qa_latest_brepmfr_task` (SHA + read-time model result validation). A new **read-only** `qa_public_automatic_ml_fallback` returns an effective `r12_fallback` for that exact opt-in automatic failed run only. This never overwrites its archived actual ML failure. Manual and unrelated runs still show `failed` as before.
5. The existing frontend `watchAutoMl` displays a truthful model failure reason before invoking the existing `watchAutoR12`, instead of claiming only that the model was “unready.” R12 predictions remain labeled `research_not_for_production`, and are never substituted for the conservative independent OCP through-hole judgment.

## Direct production control-flow regression tests
- `src/tests/test_lbracket_p3_ml_runtime_fallback.py`: extract and execute actual production `execute_ml` and latest readback helper with a **synthetic** crashing subprocess, self-owned mock STEP/weights and injected existing R12 launcher. Assert correct fallback, manual opt-out, switched CAD, modified STEP bytes, unavailable R12, start failure, and no changes to original owner-labeled files / FEA state. This cannot prove physical Windows worker compatibility or native ML correctness.
- `src/tests/test_lbracket_p3_ml_runtime_fallback_ui.js`: exercise existing frontend automatic watcher on synthetic fallback/failure/stale CAD responses. A failed native BrepMFR does not get relabeled “success”.

## Required real acceptance later
On the same original `L_bracket_correct.step` with SHA bound to CAD/FEA case, review the installed BrepMFR worker imports/checkpoint. If its actual inference errors, verify ONE fallback to installed local R12 and explicit status. If old BrepMFR completes but incorrectly calls the through-holes “blind,” **record ML accuracy unresolved**: fallback is for runtime failures only, not silent replacement of mistaken but completed predictions. CAD measurements and four OCP through-hole states stay separate from any uncalibrated ML labels. Preserve existing Windows private modules and SQLite evidence.

## Next order
P4 local rules-only AI → verified current FEA HTML report/safe archive reopen; then one combined Windows original L-bracket end-to-end acceptance that also checks P1 original INP/STA/FRD and P2 3D GPU visualization. Do not preempt this with new universal ML research.
