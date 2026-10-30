# GeoField L-bracket P4 — same-run rules Agent, HTML report and saved FEA record

Date: 2026-10-29. Strict original L-bracket-only source audit and minimal patch.

## Already shipped; do NOT duplicate
1. `gf_current_verified_report(uid,as_html=True)` selects current CAD, existing (or explicitly restored) FEA run, re-imports that run's actual INP/STA/FRD, reconciles stress/displacement and mesh counts with the on-screen summary, and checks run/case/CAD SHA before composing any HTML. The existing report integrates current rules-only `gf_current_report_agent`, `gf_render_live_agent_report` and verified A08 evidence. This **never calls paid DeepSeek**.
2. The existing `GET /api/results/report/<uid>` performs report preview; the explicit same-origin `POST /api/results/report-save/<uid>` renders its own fresh verified report and stores immutable HTML. No client-supplied stresses/HTML accepted.
3. Previously saved genuine FEA records use `r184_verified_archive_numbers` with read-only SQLite inspection and `restore_payload` independent INP/STA/FRD reread; `/api/history/verified-report/<snapshot>` also builds a revalidated report. The optional history restore requires explicit user choice. Do **not** delete or mutate saved runs as part of first L-bracket acceptance.
4. `/api/agent/evidence/<uid>` already rejects same-CAD FEA run changes during a potentially slow rules/optional LLM response. Legacy BrepMFR and R12 are research diagnostics, and must not become verified CAD holes or solver results.

## Concrete P4 integration defect found and fixed
Before this patch, `gf_current_verified_report` took the last FEA task at start, but while rules-Agent report rendering was in progress, the user could launch **another FEA run on exactly the same L-bracket and case SHA**. The original completed run remained completed and had identical CAD/case SHA, so final source checks and explicit report-save checks could return/export **the previous run as the current report**. The agent route had newer-run gating; report preview/export did not.

Added a small read-only `qa_report_active_run_unchanged(uid,cad_sha,run_id,case_sha)` that:
- Requires active completed CAD, unchanged pending import identity and exact original STEP SHA.
- If a genuine prior FEA restore is explicitly selected, requires the very same restored run ID; otherwise requires the *latest* FEA run of that CAD SHA even when the newer run is merely queued/running/failed.
- Checks latest selected run is complete and is tied to the same CAD ID, SHA and case SHA; rejects misleading summaries during a newly started or changed run.
- Is called after current rules-Agent HTML generation **and again inside the explicit immutable save lock immediately before writing**.
- Makes no solver calls, no ML retraining, no new report files until a request passes, no new UI and no user STEP/FRD/SQLite edits.

New test `src/tests/test_lbracket_p4_live_report_run_race.py` executes the real helper, simulates current L-bracket run A and same-case run B entering queued/running/complete/failed states, checks explicit restored-run selection survives without being mislabeled, and statically asserts both actual preview and save production routes invoke the same gate.

## What is NOT proved
Existing owner Windows recording displayed the original L-bracket and its real C3D4 run (≈ 49.03N +X; 7,303 nodes / 26,079 tets; max displayed 18.860339 MPa stress / 0.03309294 mm displacement), but actual private installed INP/STA/FRD and an end-to-end current L-bracket **AI + saved HTML + real record reopen** have not been executed in this repository session. CI synthetic evidence cannot prove physical installed FreeCAD/Gmsh/CalculiX, WebGL or report/save path. Existing numbers must not be mixed with a separate public C3D10/-Z study or used for safety certification.

## Next P5 (ONE Windows end-to-end acceptance)
- Inspect current user installed version/26-file SHA update compatibility and keep private modules, SQLite and original STEP backups.
- Load **existing original L-bracket**, verify four Ø5.5 CAD candidates and independent OCC through-hole evidence where available.
- Check ML automatic success/failure/R12 fallback transparently (completed wrong epoch43 label is **not** fixed by P3); do not require a newly trained model.
- Verify the real C3D4 run's actual INP/STA/FRD material/constraints/load, 3D stress vs surface hotspot and displacement; test same-run rules Agent/HTML report + one safe read-only archive reopen.
- Report user-Windows failures without multiple repeated physical test cycles. No paid DeepSeek call is necessary.
