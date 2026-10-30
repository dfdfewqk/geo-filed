# L-bracket v1 completion — P1 FEA evidence recheck audit (2026-10-29)

## Do not confuse existing Windows evidence with GitHub simulation
The owner's October 28 video showed one real L-bracket FE case using C3D4 (7,303 nodes; 26,079 tetrahedra), +X applied force about 49.03 N, and displayed max nodal von Mises 18.86033913056961 MPa and max displacement 0.03309294362799505 mm. **The video is NOT a copy of this run's actual INP/STA/FRD**; current independent reread of owner-supplied files remains pending. Do not reconstruct a supposed production FEA input from screenshots. The reference public L-bracket C3D10/-Z simulations use *different material/loading/constraints* and are not comparable.

## Actual source flow inspected
1. `execute_fea` runs `run_real_fea` or an installed external Gmsh worker, archives `case.json` and `result.json`, then invokes `reverify_task_for_display` against the same original CalculiX INP, STA, FRD before recording complete.
2. `/api/fea/status/<run>` checks current CAD task/case and re-runs `qa8_verified_completed_fea_status`.
3. `/api/fea/field/<run>` independently invokes the private installed `fea_previous_import.verify_directory`, cross-checks active case/step/run, original field arrays and stress/displacement against task, then rejects stale CAD or source changes.
4. Current summary/report calls `reverify_task_for_display` and `r125_reconcile_current_fea_summary`. Only verified same-run values qualify for HTML report/Agent.

**No code evidence of a need to rerun the numerical solver merely to display one preserved, independently reverified result**. A later Windows physical check must confirm its installed `fea_previous_import` module and saved genuine run files exist.

## Corrected P1 source defect
The old `fea_result_trust_gate._reject` suppressed stale `result`, `field`, `surface_field` but retained task-level `source_validation='INP_STA_FRD_reverified'` and `field_visualization={'available':True}` when an already-complete run failed re-verification. That was contradictory and could leak a false old "3D ready" / "verified" status to a less-strict downstream consumer. Now failed verification removes both task-level flags **in addition** to all unverified fields/numeric results, while preserving failure status, run identity and original archive files. The existing still-running/failed path already removed these markers. No stress numbers, solver cases, material coefficients or user files changed.

Added `src/tests/test_lbracket_p1_fea_failed_source_flags.py` executes the actual source module on temporary self-labeled **synthetic placeholders** with injected verifier, and checks missing FRD, wrong case SHA and pending state. Synthetic test success is NOT proof of an owner's genuine 49.03N solution or Windows installed model.

## Remaining prioritized steps
1. **P1 not fully closed**: actual original installed L-bracket case and INP/STA/FRD hashes/physical input identity need private Windows read-only inventory and final one-shot acceptance. Verify saved material, constraint faces, load direction/force, mesh type, run+case SHA, reported values. No fabricated reproduction from screen.
2. P2 existing verified FRD 3D contour, peak/marker and displacement scale, same run ID; screen matching.
3. P3 original BrepMFR/R12 research diagnostic status for exactly original STEP; uncertainty and existing misclassification remain visible, do NOT retrain.
4. P4 rules-only Agent, verified HTML report one export and read-only saved-run restore. DeepSeek is optionally consented and not needed for the main flow.
5. P5 existing 26-target Windows updater compatibility and final single original L-bracket run, preserve all historical CAD/SQLite/FRD/checkpoint.

**No new CAD family, ML weights, default solver setting or windows-installed files were modified.**
