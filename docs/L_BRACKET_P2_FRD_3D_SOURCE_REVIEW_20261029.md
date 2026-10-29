# L-bracket v1 — P2 verified-FRD 3D source review (2026-10-29)

## Scope
One owner's already-existing L-bracket only. No new CAD, geometry fixes, solver iterations, training, weight changes, safety certifications, Windows file edits, or new menus. **Current source reviewed; this is not an installed-Windows live graphics test.**

## Existing rendering paths verified by source
- `/api/fea/field/<run>` checks current job, CAD SHA, case SHA, run identity, independently calls the installed `fea_previous_import.verify_directory` for actual CalculiX INP/STA/FRD. It invokes `qa_bind_verified_fea_field` and `validate_surface_evidence` and checks same-run maximum stress/displacement before returning surface arrays.
- `setFeaField` rejects mismatched CAD/run/case, invalid stress/displacement mm arrays and independently verified surface maximum positions before activating the GL and Canvas2D field.
- `gfVerifySurfacePeakEvidence` checks raw surface node index + stress + coordinate + absolute MPa source and explicitly refuses pretending the surface peak pin is a true verified viewer CAD face or global/internal max location.
- `gfVerifyDisplacementEvidence` separately validates actual mm displacement magnitude, peak coordinate and global value. Geometry multiplier ×1, ×5, ×20 never scales the physical stress or displacement labels; camera transform retained on mode changes.
- Archived verified FEA preview independently rereads evidence and retains explicit same-run/3D safety limitations.

## Corrected confirmed P2 wording bug
`feaStressScaleStatus()` said **`실제 현재 최대`** next to `feaField.maxStress`. But `feaField.maxStress` is max stress **only of rendered surface nodes**. The solver's true whole-model FRD maximum `feaField.peakEvidence.globalMax` can be larger (interior). For the original L-bracket this distinction is material to whether the hotspot is on a shown face.

The updated existing legend explicitly reports:
- the displayed surface color scale ceiling (0..N MPa, optional manual/compare clipping),
- **표시된 표면 최대 (MPa)**,
- **전체 절점 최대 (MPa · 전체 최대 위치 미검증)**, taken only from already validated A06 global evidence,
- and warns that manual saturation is merely a color choice, **not a solver value change**.

No physical numbers are invented; if the global evidence is not present the label says `미확인`. New `src/tests/test_lbracket_p2_stress_legend.js` invokes the real production browser helper for synthetic 8 MPa surface versus 13 MPa global, verifies unclipped/manual-clipped labels, no FRD mutation and no contour state leakage.

## P2 remaining real acceptance
The user's original October 28 Windows recording showed C3D4 with 7,303 nodes/26,079 tets, total ~49.03 N +X and visible max nodal stress ~18.860339 MPa and displacement ~0.03309294 mm. **That screenshot does not independently provide the full original INP/STA/FRD or prove hotspot coordinates on the real installed screen**. The final Windows acceptance should verify:
1. that same exact CAD SHA, FEA case SHA and run ID match physical solver files;
2. surface maximum hotspot coordinate is visible, color legend shows both surface and whole-node maximum, and any difference is explained;
3. switching stress/displacement, ×0/1/5/20 geometry deformation and rotating the current camera neither alters numerical FRD values nor loses the current run;
4. 3D view failure remains clearly a 3D-loading error without declaring the already verified numerical FEA calculation invalid.

## Next
P3 original BrepMFR/R12 research ML linkage for this exact L-bracket, no training. P4 same-run rules AI/report/history, then one Windows physical acceptance. **P1 actual original solver-file acceptance and P2 real display acceptance still pending**. Never claim structural safety or mesh convergence based solely on this change.
