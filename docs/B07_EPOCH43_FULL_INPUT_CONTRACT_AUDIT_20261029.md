# B07 STEP 1 — epoch43 input/encoder contract forensic audit (2026-10-29)

## Decision / scope
Read-only audit and isolated real-checkpoint experimentation **only**. The original private epoch43 file, the owner's installed Windows worker, CAD/FEA/SQLite, and the GitHub deployment manifest were not changed. No model quality improvement is claimed.

## Three distinct compatibility layers (do not conflate them)
1. **Official public MFTRCAD training examples**: `graph_face_attr` is 14-d with surface one-hot in the first 6 entries, area at 9, and centroid at 11:14. Edge attr is 15-d with flags/length in the published positions, and face UV grid is 7×10×10 with trim validity mask. Published upstream `brepformer/pipeline_analysis.md` documents mismatch with its STEP converter and large performance drop.
2. **Private archived OCP STEP converter (Oct-15 ZIP)**: `normalize_geometry()` emits the one-hot face layout, area at index 9, center at 11:14 and a transformed 15-element edge record. But **after that conversion**, `step_to_preprocessed_sample()` obtains centroids from `face_attr[:,2:5]` and normals from `face_attr[:,7:10]`. These are no longer centroid and normal channels. `precompute_graph_features()` still computes D2 and angle tensors, so tensor presence/shape checks alone cannot find the problem. The original private converter also samples UV trims differently from the published corpus.
3. **Reconstructed private inference model**: The archived `legacy_architecture.py:OldGraphNodeFeature.forward()` interprets the same face attribute tensor as scalar surface type at index 0, area at 1, centroid at 2:5, rationality at 5, loop count at 6. **This directly conflicts with the preceding converter's one-hot output.** Original checkpoint tensors load strictly into that reconstructed module, but that alone does not establish the original training-time forward operation. It is unsafe to 'fix' the model's layer inputs solely by changing indexes.

## Measured actual checkpoint tests
An isolated runner loaded the exact private research checkpoint SHA-256 `50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1` using the reconstructed worker and compared three descriptor inputs on the **same 4 STEP files / 34 total faces**. This does not access the owner's installed Windows ML:

| Input variant | Total changed final face classes vs archived baseline | Maximum absolute class-probability change across 4 STEP cases |
| --- | ---: | ---: |
| Archived wrong offsets | — | — |
| Corrected center (11:14) and UV mean normals, no UV point sampling | **0 / 34** | **0.00648** |
| Same corrected center/normals, plus UV-grid D2/angle point sampling | **0 / 34** | **0.02331** |

Individual cases: `two_through_holes.step` 8 faces, `one_blind_hole.step` 8, `plain_solid.step` 6, `L_bracket_previous_2026_09_23.step` 12. The two through-hole cylinders remained predicted `blind_hole` in every descriptor variant, the blind-hole cylinder remained `blind_hole`, and four L-bracket cylinders kept their respective classifications. These are **synthetic design expectations, not an independent labeled industrial accuracy test**. Changes in probabilities show the descriptors reach the model, but correcting their layout **does not solve the observed hole misclassification on these cases**.

Earlier actual-checkpoint tests using 12 upstream *labeled* public sample graphs (363 faces) found original one-hot graph layout 209/363 exact face labels and archived scalar feature remap 46/363; through 10/10 vs 3/10, blind 17/22 vs 21/22. Those upstream samples may overlap training and are **not a held-out score**.

## Decision for next step
1. Before touching the checkpoint, determine and version-lock **the original model's true training-time forward-pass semantics**, not merely the available tensor keys. Check against original source commit/config and labels. If unverifiable, mark its training compatibility *unknown*, do not silently rewrite the network.
2. Perform an isolated controlled same-STEP ablation of the **entire input contract**: face type/area/centroid, edge attribute flags, normalized x/y/z, UV trim masks and sampling window, D2 and angle descriptors. Keep expected graph face order/label mapping explicit. Evaluate both through and blind cases and an unchanged no-hole control.
3. Only if the entire contract can be reconstructed and *held-out labeled* STEP performance is acceptable, consider keeping epoch43. Otherwise regenerate training graphs with the **same deployment converter** and retrain with properly held-out CAD families. Do not mix publicly sampled graph evaluation with prospective production performance.
4. The already-merged independent conservative OCC solid-occupancy display continues as a separate CAD diagnostic, NOT a replacement for the ML classification model.

## Shipped read-only enhancement
`src/ml_runtime_source_review.py` now records `full_input_contract_review` from AST inspection of the locally archived converter and legacy network source **without executing them**. It distinguishes wrong centroid/normal offsets and the apparent converter/reconstructed-network face attribute disagreement; every result explicitly sets `trained_model_equivalence=false` and `real_step_accuracy_verified=false`. It never hashes or copies private checkpoints beyond its existing SHA-only fingerprint. Unknown worker/source variants are not labeled as the archived version.

Note: the upstream project also documents D2/angle omission at two places in its older pipeline; the current ZIP converter already outputs both tensors. Therefore **missing tensor vs incorrectly populated tensor** are different failure modes. Review `brepformer/pipeline_analysis.md` in `cad-results/BrepMFR` and the project-specific original source.
