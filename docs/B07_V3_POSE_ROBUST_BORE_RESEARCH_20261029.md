# GeoField B07 Step 7 — pose-robust bore model v3 research (2026-10-29)

## Executive result / release verdict
**New research-only face model performed better on the tested synthetic CAD + rigid-transform examples, but is STILL NOT APPROVED for real GeoField Windows production, 27-class BrepMFR replacement, FEA or AI evidence.**

A new random-forest classification baseline uses intrinsic, geometry-centered 39-element features: surface type/normalized area, *eigenvalues* of centered face XYZ and face normal samples, UV directional magnitudes, relative neighboring-face distances and dot-products, and relative edge-type distribution. **No absolute centroid XYZ, global coordinate-normal direction, STEP face ordinal, fixed hole label, B-Rep exit occupancy or ML confidence is an input feature.** In exact arithmetic many expressions are invariant to rigid transform; independently reimporting STEP can change UV parameterization/seams, so the complete implementation is **pose-robust in tested conditions, not mathematically strictly invariant to all rotations**.

## Data isolation
- Previous research 252 STEP designs from **14 previously inspected** geometry families were used **only as TRAIN**. This includes all previously evaluated `u_channel` / `web_bridge` cases — these are **NOT counted as fresh validation/test again**.
- 108 *additional* STEP pose entries across **6 genuinely new geometry families**, all disjoint from those 14:
  - TRAIN: `offset_buttress`, `side_pillars`: 36 original STEP cases.
  - VALIDATION: `staggered_fins`, `step_bracket`: 18 original CAD designs + 18 X90/translation clones = 36 STEP entries.
  - FROZEN TEST: `railed_cantilever`, `opposite_webs`: 18 original CAD designs + 18 X90/translation clones = 36 STEP entries.
- **360 total STEP entries** referenced: 288 train + 36 val + 36 test; **36 val/test pose entries are not independent CAD parts**. Per class in test: 6 independent through and 6 independent blind designs, each tested twice with a posed copy.
- The SHA-pinned existing archived private OCP converter `6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46` was used in the isolated local environment. The 108 new files passed actual STEP→graph conversion, finite/shape/adjacency checks and generator-defined unique cylindrical bore-face identification. Original and rotated sample files stayed within the same split. Ground-truth labels are the CAD generator's scripted cut intent; no model/B-Rep inferred targets.
- Three model candidate settings (`n_estimators=200`, `min_samples_leaf/max_depth`: 1/4, 2/6, 2/10; seed 712029) were selected solely by **validation hole-only macro F1**. All three scored 1.0 on validation; deterministic tie break chose `min_samples_leaf=1,max_depth=4`. Only AFTER this choice did the code first evaluate the frozen new test.

## Actual new test (fixed trained model)
| Holdout metric (synthetic) | Result |
| --- | ---: |
| Validation class confusion [other, through, blind] | `[[204,0,0],[0,12,0],[0,0,12]]` |
| Frozen new test class confusion [other, through, blind] | `[[192,0,0],[0,12,0],[0,0,12]]` |
| Fresh synthetic test original bores | through **6/6**, blind **6/6** |
| Paired X90 + translation bores (same CAD designs) | through **6/6**, blind **6/6** |
| Both test geometry families | through 6/6 and blind 6/6 in each *including pose copies* |
| Per-class precision/recall/F1 (on supervised face rows) | all 1.0 |
| False confidence or safety claim | **none** |

The test's `192 other` counts *supervised faces* belonging to 12 STEP entries (=6 original no-hole designs and 6 pose clones), **not 192 independently labeled parts**. The 3-class output is NOT the old 27 classes; on positive-hole CAD only the one generator-known bore wall is labeled, all other faces are ignored.

### Separate fixed-checkpoint stress on rotations not used for model selection
After freezing the model, additional **12 STEP pose variants** (X37°, Y67°, Z137° + translations) were generated from 4 already-reserved *test designs* (two families × two hole types; same designs, NOT 12 new parts). Through **6/6**, blind **6/6** predictions correct. The original/X90 paired bore feature vector L2 difference was at most `4.88e-7`. However for some Y67/Z137 STEP reimports the vector's L2 difference reached **1.7007**, despite unchanged class predictions. This is a concrete warning that regenerated OCC surface UV parameterization is not guaranteed representation-invariant; do **not** claim universal SE(3) equivariance.

### Existing previously seen STEP diagnostic, not independent validation
With the frozen research model:
- `L_bracket_previous_2026_09_23.step`: through cylinder predictions **4/4** (previous model 3/4).
- `two_through_holes.step`: **2/2** (previous model 1/2).
- `one_blind_hole.step`: **1/1**.
- `plain_solid.step`: zero cylindrical faces, not an ML false-positive-rate claim.
- `sample_bracket.step`: 4 cylindrical predictions `through,through,blind,through`; no verified full face-level ground truth and **no accuracy claim**.

This is useful evidence of improved behavior on a few remembered examples, but **not an independent generalization score**, since these files were consulted during prior development.

## Private artifacts and reproducibility
- Local-only research model `research_pose_invariant_rf_v3.joblib` is **304,657 bytes**, SHA-256 `74c0ac185692697d483c2fd5953606c2ed056f3ea1acc43dfe3dde90963bc340`. `joblib` relies on pickle and is NOT safe to load from untrusted sources; do not automatically load or publish it as a new engine runtime. The model is **not** uploaded to GitHub or deployed to Windows.
- A private local `v3_dataset_manifest.json` describes the new STEP instances and family/pose grouping, and `evaluation.json` captures the validation selection, frozen test and per-pose confusion.
- Checked-in source `src/research/brepmfr_v2/invariant_features.py` implements 39 graph-relative invariant features. `train_pose_invariant.py` offers an opt-in *separate research* training/evaluation command accepting the owner-provided previous/new manifests. All new model sources remain outside the 26-file Windows installer. CI tests do not need private CAD, converter or checkpoint.

## Next acceptance requirements
**Do not promote** this model based on the small generator-only test. Required before application integration: an **independently curated, face-labeled real industrial CAD dataset**, multiple axis orientations/translated STEP reimports and **non-cylindrical/stepped/counterbore** negatives, calibrated abstention where necessary, real Windows inference proof, verified graph-face-to-viewer ID mapping, and per-class metrics with adequate independent CAD family count. Preserve the independently verified conservative OCC solid-occupancy through/blind diagnostic and keep all ML, CAD, FEA and optional AI conclusions separate.

No user Windows installed files, private old epoch43 weights, 26-file update installer, existing CAD/FEA/3D/AI behavior or saved records were changed.
