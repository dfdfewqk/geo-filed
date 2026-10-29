# GeoField B07 — conservative STEP B-Rep through/blind evidence (2026-10-29)

## Problem and deliberate separation
The private epoch43 BrepMFR model is not validated for production hole typing. Its re-created STEP preprocessing differed from the upstream MFTRCAD graph input and yielded wrong through/blind predictions. **This change DOES NOT correct or relabel the neural network.** Instead the existing CAD geometric-measurement UI now offers a separate, explicitly labeled, local OpenCASCADE solid-occupancy assessment.

## What was implemented
- `strict_brep_hole_evidence(step_copy,sha)` is called **only during actual OCP CAD import**, before the import's disposable STEP copy is deleted. It verifies the input SHA before/after and does not require a private checkpoint, GPU, DeepSeek, or any AI service. No additional Python module/package file is introduced; the 26-target update manifest remains unchanged.
- Support is intentionally narrow: exactly **one solid**, one **full circular cylindrical face**, a sufficiently long nondegenerate axis, three interior axial slices void of solid material, and **two consistent samples** immediately beyond each cylinder end at the axis and eight radial positions. Unambiguous OUT/OUT means through; OUT/IN or IN/OUT means blind; other cases abstain. Multi-solids, partial/stepped counterbore sections, boss exteriors, missing OCC and geometry errors are not called holes.
- Results are bound to the active CAD job and exact SHA and returned at `/api/geometry/hole-evidence/{cad_job_id}`. The `geometryDimBtn` view includes independent B-Rep results only after rechecking current ID/SHA. There is **no viewer-face mapping**, no face highlighting, no FEA or ML writes, no automatic DeepSeek call, and no interpretation as a structural safety certificate.
- Optional OCC classification errors are caught so the existing CAD, saved report, FEA and history continue unaffected. FreeCAD-only runtimes report unavailable rather than fabricate OCC evidence.

## Real local test (not a general accuracy claim)
Read-only Oct-20 user-owned research ZIP synthetic STEP files processed in an isolated Linux OCP runtime; the actual learned epoch43 checkpoint was **not used** for these geometry observations. 68 models were examined in a stress harness. Design-specific unambiguous cases:
| Design family | Expected from generated design | Observed |
| --- | --- | --- |
| Test chamfer plate/L support, 12 files | through-hole | 12/12 through-hole |
| Test chamfer plate/L support, 13 files | blind-hole | 13/13 blind-hole |
| No-hole, 12 files | no cylindrical-hole evidence | 12/12 no hole |
| L_bracket.step | four full through cylindrical hole faces | four through states |
| two_through_holes.step | two through holes | two through |
| one_blind_hole.step | one blind hole | one blind |
| counterbore_blind.step | stepped outer bore + blind inner bore | outer unverified, inner blind |
| counterbore_through.step | stepped outer bore + through inner bore | outer unverified, inner through |

Stress cases included rotated/side holes and mixed holes. Ambiguous or external cylindrical geometry was deliberately left **unverified**, not assigned to a class to increase an apparent success rate. Design filenames are **not independently annotated face-level industrial ground truth**, and this is not a calibrated model accuracy metric.

## Remaining work
The original neural BrepMFR classification quality, all industry geometries, actual user-installed Windows runtime, visual face ordinal mapping and end-to-end FEA/AI UI are **not yet proven**. This conservative display fallback addresses the user's practical through/blind ambiguity only for supported STEP geometries; neural evaluation/retraining requires a legitimately held-out labeled dataset and original training provenance.
