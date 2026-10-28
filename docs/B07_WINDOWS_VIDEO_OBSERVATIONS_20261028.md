# GeoField B07 — User Windows screen recording review (2026-10-28)

## Scope and provenance

A 108.67-second, 1910×1016, 30 FPS user-supplied Windows screen recording was reviewed at 4-second intervals and full-resolution selected times. This is **screen evidence only**, not a copied STEP/INP/STA/FRD archive, actual executable instrumentation or proof of structural safety. The recorded web app is `http://127.0.0.1:8600`.

### What visibly worked

- A real STEP named `L_bracket_correct.step` loaded and rendered as a shaded interactive L-bracket; the current CAD-only HTML report showed B-Rep bounding box **50×30×50 mm**, volume **8444.90047 mm³**, surface area **6599.27876 mm²**, four 5.5 mm through-hole candidates.
- The FEA page showed fixed face selection and +X 5 kg equivalent applied force **49.03 N**; recorded run ID **268ead97e9314a89b68b3c1162d1d4fd** (redacted from public screenshots outside the user's clip), **7303 mesh nodes**, **26079 tetrahedra**, C3D4 type.
- The user viewed an actual CalculiX-reported maximum nodal von Mises stress **18.86033913056961 MPa**, maximum displacement **0.03309294362799505 mm**, rotated the 3D model and displayed FRD-derived stress color ranges and surface hot spot.
- The current CAD integrated HTML report opened in a new browser tab and the result/history views rendered without a terminal error.

### Bugs and presentation issues actually supported by the recording

1. The appended A08 report row **하중 방향: 확인 불가** was shown despite a matching +X face-load vector and numerically reverified 49.03325 N; source bug confirmed: the reporter passed a Python `list` to `_text`, which accepts only scalar values. This **always suppressed valid list-form directions**. Fixed with bounded finite **unit-vector** display in `fea_report_a08.py`.
2. The appended report also displayed **메시 요소: 확인 불가** even while the user-facing FEA result showed C3D4. For old saved-case schemas without `mesh_request.element_type`, the A08 reporter had no independently verified mesh-type fallback. Fixed by propagating the actually reverified solver mesh `element_type` into `r124_case_provenance`; report labels requested type separately, never invents a solver-verified type, and explicitly warns on mismatch.
3. The results panel's report button used to show a conditional explanation referencing **HTTP 409** immediately after opening a new tab. **That is not evidence of an actual 409 response**, and the recorded report opened successfully. Replaced with “report requested; verify actual response in new tab” and updated the frontend test. Do not claim a report failure on the basis of that old hint.
4. The red FRD hotspot marker represents a verified **surface node projected onto the 2D viewport**, NOT a visibility-tested intersection with the CAD surface. The label now explicitly notes **occlusion unverified**, preventing a misleading impression that a hidden 3D surface location was physically identified from the current camera angle.

### Not proven by this recording

- No independent 3-mesh convergence, stress singularity study, structural safety certification, or FEA field-to-CAD face occlusion registration.
- No actual user-paid DeepSeek call is shown. ML model reported **research prediction with accuracy unverified**; the independent R12 model did not visibly complete on this newly loaded STEP.
- No complete **saved immutable HTML POST response** or archive import/deletion integrity check was shown; a current-session HTML GET was visibly successful. Do not conflate these workflows.
- Installing this exact corrected branch on the user's Windows runtime, comparing solver result invariance before/after the UI/report change and final B07 acceptance remain pending.

## Regression coverage

Tests include real frontend UI handler smoke tests, A08 HTML vector/solver-mesh evidence tests, negative invalid-vector and conflicting mesh type cases, prior B03 surface peak/evidence contracts, and full A11 Linux/Windows temporary safety suites. No synthetic fixture is labeled as a user-file solver test.

This fixes **report provenance and honest annotations only**; never change the CAD, applied load, CalculiX solver, FEA result files, archived records or ML weights to match a reported display value.
