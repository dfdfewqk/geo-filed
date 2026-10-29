# B07 Step 2 — epoch43 real-checkpoint full-input 24-variant ablation (2026-10-29)

## Decision
**No tested input combination is safe to promote to GeoField's default BrepMFR prediction path.** Preserve the original private checkpoint and installed inference files unchanged. The existing separate conservative OpenCASCADE B-Rep through/blind/unknown diagnostic stays available and must not be conflated with neural model improvement.

## Verified experiment boundaries
- Isolated Linux CPU environment; real private checkpoint SHA-256 `50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1`; loaded through **reconstructed legacy** BrepFormer network, which strictly loads tensor weights but is **not proven training-forward-equivalent**.
- Owner-owned previously generated research ZIP provides 36 synthetic STEP designs: 12 through-hole, 12 blind-hole and 12 no-hole, from two CAD families (chamfer_plate and l_support, indices 00–05). **No independently labeled per-face ground truth**, and closely related procedural designs do not constitute an industrial benchmark.
- Each STEP underwent 24 real model forward passes: face attributes {archived scalar, published-like onehot} × edge attributes {archived 15-slot flags, reconstructed scalar type/length/angle/convexity in model-consumed slots} × UV {archived trimmed-unpadded, explicit trim-unpadded, 10% padded+trimmed} × graph descriptors {archived D2/angle, corrected centroid+UV-grid-sampled D2/angle}. **36 × 24 = 864 actual inferences** over 360 face occurrences, with 24 expected cylinder-hole face occurrences. No retraining or installer execution.
- The "raw edge" experiment is a reconstructed candidate, **not evidence of the exact original training data layout**. The "onehot" candidate is intentionally fed to a reconstructed network that expects scalar type fields; success on any design cannot prove correct semantics. Consistent global normalization was held constant when evaluating UV changes.
- The experimental padded-UV path retains the recovered converter's behavior of zeroing masked-out xyz samples. Published upstream MFTRCAD examples may retain underlying surface geometry at masked positions. Thus even **10% padded+trimmed is not guaranteed MFTRCAD-equivalent**, and this is not an implementation-ready model fix.
- All 36 × 24 model inference combinations executed; no runtime failures. Only exact predicted class for the known cylindrical face was compared against the synthetic design's intended hole type. The absence of cylindrical faces in a no-hole STEP is a **geometric fact**, not a model success statistic.

## Observed results
| Research input variant | Through cylinder matches | Blind cylinder matches | No-hole designs with zero cylinder faces |
| --- | ---: | ---: | ---: |
| archived `scalar/flags/old/legacy` | **0 / 12** | **12 / 12** | 12 / 12 |
| `onehot/raw/old/fixed` | **0 / 12** | **12 / 12** | 12 / 12 |
| `scalar/raw/trim10/fixed` | **0 / 12** | **10 / 12** | 12 / 12 |
| **best on these synthetic designs:** `onehot/raw/trim10/fixed` | **6 / 12** | **12 / 12** | 12 / 12 |

The candidate's **6 / 12 through-hole** matches are all from the **l_support** family (6/6); all six **chamfer_plate** through cylinders were incorrectly classified as `6sides_pocket`. Holding back indices 02–05 within these same two design families does not improve generalization: candidate on those eight through designs is 4/8. The two descriptor choices in the most promising layout yielded the same final cylinder classes.

For the *no-hole design* set, the best synthetic candidate classified **0 non-cylindrical faces** with a `through_hole` or `blind_hole` class versus 52 under the archived baseline. Do **not** call this a true false-positive rate: the 27-class machining-feature segmentation may assign feature labels to planar parts of a hole and per-face truth was not provided.

## Counterexamples on other STEP geometries
The same best candidate was then applied to five separately preserved CAD fixtures (not the same 36 procedural files):
| CAD fixture | Archived reconstructed model on cylindrical surfaces | Candidate `onehot/raw/trim10/fixed` |
| --- | --- | --- |
| Historical L-bracket (4 cylindrical surfaces) | stock / through_hole / blind_hole / blind_hole | **Oring × 4** |
| Two-through-holes specimen (2 cylinders) | blind_hole × 2 | **rectangular_pocket × 2** |
| One-blind-hole specimen (1 cylinder) | blind_hole | blind_hole |
| Plain solid | no cylinder | no cylinder |
| Another bracket specimen (4 cylinders) | blind_hole × 2 / stock × 2 | circular_end_pocket × 2 / blind_hole × 2 |

This **directly rejects production promotion** of the synthetic-design leader. The L-bracket's four bores and the two-through fixture get worse or remain incorrect; the model has not been repaired.

## Actual cause hypothesis and required next milestone
The original Oct-15 STEP converter emits onehot face tensors and edge flag tensors yet the reconstructed old network consumes scalar face type (index 0), scalar edge type (index 0), edge length (index 1), dihedral (index 8) and convexity (index 9). Descriptor indices also differed and UV trim sampling is off-distribution from MFTRCAD's published graphs. These are verified code-level inconsistencies, but the **checkpoint's true original training-time network forward** remains unproven; arbitrary index rewiring is scientifically unjustified.

Proceed only after identifying genuine checkpoint/source/config provenance and graph-label face mapping. If exact training-equivalent inference cannot be reconstructed and demonstrated on **independently held-out STEP CAD families**, generate graphs using the identical deployment converter and run a **new versioned training or fine-tuning experiment** with family-separated train/validation/test. Report both through and blind classes, rather than optimizing one class alone.

## Security / scope
Experiment files (including source references, full per-case output and the user's private 76 MB checkpoint) remain **local/private** and are not pushed to GitHub. This documentation contains aggregated observations only. No production model weights, ML predictions, Windows installed code, CAD originals, SQLite/FRD, FEA, solver behavior, deployment manifest, or AI provider calls changed in this PR.
