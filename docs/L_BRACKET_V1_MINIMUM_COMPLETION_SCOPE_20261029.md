# GeoField v1 L-bracket-only — minimum completion scope and acceptance gates

Date: 2026-10-29. Base: `work/geofield-ab-ai-c3d10-integration-20261026`.

## Explicit goal
Finish the existing user L-bracket's ONE coherent workflow:
**STEP import → measured CAD dimensions and four hole candidates / separate conservative B-Rep through-hole evidence → same-STEP ML research status → ONE existing real FEA case → FRD-backed stress/displacement 3D → rules-based AI and verified report → safe reopen.**

This is a **scope reduction for completion/testing**, NOT permission to delete the user's code, advanced tools, historical results or original model. Do not add unrelated CAD families, architecture, training, menus, or new engineering claims. Previously approved 102 design points stay in source; the first complete L-bracket path is the priority.

## What is already implemented / observed, versus still open
| Area | Evidence already available | Exact remaining acceptance |
|---|---|---|
| CAD | User's earlier Windows video visually showed original L-bracket, 50 × 30 × 50 mm, volume 8444.90047 mm³, surface area 6599.27876 mm² and four Ø5.5 cylinder candidates | Verify current imported original STEP is same SHA; original is not silently replaced; distinct B-Rep verification reports four **through** states only when OCP independently supports them |
| ML | Existing legacy epoch43 worker integration and signed local R12 fallback; previous research showed through/blind confusion. Latest ML API SHA revalidation/terminal error handling merged PR #66 | Confirm ONE user's original STEP goes through installed inference with same CAD SHA and a truthful success/error/research status. Neural predicted labels do **not** become verified CAD facts. If epoch43 labels the four holes incorrectly, record **ML NOT FIXED**, not “four correct ML holes”. No general-model retraining |
| FEA | Genuine Windows C3D4 case was shown: 7303 nodes, 26079 tetrahedra, +X approximately 49.03 N, reported von Mises 18.86033913056961 MPa and displacement 0.03309294362799505 mm | First lock exactly **one user-owned case** with material, face support, force vector, mesh type and CAD/case/run SHA. Reverify real INP/STA/FRD before display. Do not substitute other public C3D10/−Z or historical 5kg/−Z results |
| Stress / displacement 3D | B03/B04 have existing FRD field, stress-marker/camera/scale guards; prior Windows video rendered stress colors | Check the same verified FEA run's 3D UI and numerical peak; distinguish surface marker vs whole-volume nodal maximum and keep user camera when mode changes |
| Agent / report | Existing locally measured-evidence rules-only AI, optionally consented DeepSeek and provenance-gated HTML summary/save | Local Agent must use same STEP and verified FEA run and report must open/save when eligible; no invented stresses or CAD faces. External paid DeepSeek call is **not a mandatory v1 acceptance step**, and is never silently invoked |
| History | Verified SQLite snapshot/restore, report, comparison and deletion code exist | Check that **one** saved verified FEA run can be reopened with same SHA/run and 3D evidence; do NOT perform real permanent deletion for this first acceptance |
| Windows update | Signed 26-file update candidate/rollback tested in temporary Linux and Windows CI; prior user's actual install had 15 SHA-mismatched local sources; compatibility migration code improved | Review actual existing local version audit once, backup/hash-lock any authorized code migration; only then a SINGLE physical Windows L-bracket end-to-end test. Repo CI alone does not establish real machine compatibility |

## Must complete — ordered, no new architecture

**P0. Before actual Windows install:** do a static GitHub route review for this original L-bracket; ensure each /api CAD/ML/FEA/3D/AI/report endpoint uses current CAD SHA and, where appropriate, the exact FEA run/case; fix only confirmed route errors. Follow existing unit suites, never mock a success as an industrial validation.

**P1. CAD (first visible proof):** on same STEP, render body and measured 50×30×50 mm, volume and four Ø5.5 candidate holes. Show independent conservative OCP through-hole assessment when supported; when absent, display "미검증" (not inferred true from BrepMFR or R12). No demand for impossible viewer-face mapping.

**P2. ML (existing flow only):** trigger/check existing original worker or existing R12 optional fallback (no v2/v3 promotion). One input, one current CAD SHA. Show only diagnostic with uncalibrated score; genuine wrong predictions remain a **known issue** and cannot be relabeled as correct. A valid no-ML/unavailable result must not block CAD/FEA.

**P3. ONE real FEA case:** preserve exact user material and boundary/load selections; reverify actual source INP/STA/FRD and show MPa/mm, actual C3D4/C3D10 identity, and an accurate contour and displacement field. A mesh sensitivity/unresolved singularity warns **not verified convergence**, but does not require automatic 3-mesh batch just to show one verified run.

**P4. Same-run AI, report, record:** use only independently measured CAD and verified FRD. Report GET/save and one non-destructive history reopen; record source SHA / FEA run / case SHA match. DeepSeek remains user-consented optional after the rules-only path works.

**P5. Final user-PC acceptance exactly once after code is ready:** verify updater compatibility, apply authorized backed-up update and run original L-bracket from import through complete above path. Record exact failed stage and existing logs if not working; do not ask user to repeat daily physical tests for each submodule.

## Explicitly OUT of first-pass completion / deferred (P2 or later)
- New CAD families, generating hundreds of synthetic STEP, v2/v3 research model retraining, and automatic model-weight replacement.
- New ML architecture, 27-class model retraining, uncalibrated ML score promotions or pretending geometry's four verified holes are four correct neural predictions.
- Full automatic three-mesh study on every case, extra C3D10 experimental surface traction branch, optimization / parametric design / mass simulation unrelated to the user's locked case. Keep existing code as advanced tools.
- Automated batch CAD analysis, multi-CAD workflows, complex counterbores, extra image generation and novel UI tabs.
- Multiple FEA run comparison, permanent history deletion, or rollback stress-tests on user-owned records during the **first** L-bracket acceptance. Preserve code/features for later targeted validation.
- Live paid DeepSeek call unless user explicitly opts in; it is a separate optional explanation, not a source of CAD/FEA values.
- Structure-safety certification, face-cause inference from a projected FRD hotspot, or claiming mathematical mesh convergence from an arbitrary screenshot.

## Definitive completion criteria
1. **Same exact original STEP SHA** across CAD measurements, visible model, BrepMFR/R12 diagnostic if run, and verified FEA case.
2. Independently measured **four Ø5.5 hole candidates**, with **through** from OCP only when actual supported geometry is verified, otherwise clear "unverified"; false old BrepMFR label is disclosed, not silently rewritten.
3. At least one **actual independent INP/STA/FRD reverified FEA run** on that STEP with original material/load/fix/element identity, matching 3D MPa/mm and report.
4. Same-run rules-only Agent + one saved/reopened non-destructive report/history without state changes or evidence substitution.
5. User's current Windows install is tested in reality after verified update and cannot lose original STEP, prior SQLite, existing runs or old checkpoint.
6. **Model quality and structural-safety limits remain explicitly labeled**. "Pipeline integrated" must never be equated with "BrepMFR through/blind classification fixed" or "FEA convergence proven."

## Operating agreement
ChatGPT performs source review, targeted fixes, tests and merges on the above steps first. Antigravity/user Windows only for missing private-runtime compatibility and final physical graphics/solver/model check. **No unnecessary new tasks**. This document changes scope and test priority only; **zero user product files deleted or features disabled**.
