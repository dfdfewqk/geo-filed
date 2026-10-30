# GeoField B07 Step 6 — family generalization, rigid-pose failure and no-promotion gate (2026-10-29)

## Result: NEW training improved synthetic family holdout, but model STILL fails pose robustness
This run is separate research on an isolated Linux CadQuery/OCP/PyTorch runtime. It reuses the **exact original archived private converter SHA `6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46`**, but neither the private converter source nor the model weights nor original STEP files are committed to GitHub or installed into Windows.

The already-consulted old six family splits were ALL moved to the new **training** partition. They were **not silently counted again as new held-out test samples**. The independent newly generated synthetic CAD families were fixed before training and evaluated only after the selected checkpoint had been frozen.

| Split | CAD families | STEP cases | Through | Blind | No-hole |
| --- | --- | ---: | ---: | ---: | ---: |
| Train | plate, rounded_plate, notched_plate, raised_edge, l_support, chamfer_plate, cross_rib, tabbed, corner_web, two_posts | 180 | 60 | 60 | 60 |
| Validation | double_fin, wing_tabs | 36 | 12 | 12 | 12 |
| New test | u_channel, web_bridge | 36 | 12 | 12 | 12 |
| **Total** | **14 disjoint design families** | **252** | **84** | **84** | **84** |

- Exactly **144 new synthetic STEP designs** were generated and converted. All new samples had valid single solids, matched generator-defined bore radius/axis when positive, and passed the face-type/normalized-area/centroid and graph finite/shape checks. The original 108 graph cases were reused unchanged.
- Newly generated **training** family cases include rigid rotations (X/Y/Z) and/or translations for some designs. Validation and new test families use unchanged initial orientation (the limitation directly exposed by later stress).
- The neural architecture is deliberately unchanged from the preceding B07 v2 CNN + face/neighbor/edge learner, seed `20261029`, AdamW learning rate 0.001, 30 maximum epochs, sqrt inverse-class-frequency weights. Pre-locked epoch selection uses **validation through+blind macro F1 first**, overall 3-class F1 second; patience=8. **Selected epoch=2; stopped after epoch=10.** New test was evaluated *once after* selecting and reloading frozen best weights.
- Distinct research checkpoint SHA `cbbaee87d04dfcd65e8b3cace06b020ba8b7e63be588adaeb1a90c963ad50853`, 33,763 bytes; `eligible_for_production=false`; this file stays private/local and is NOT installed or published in GitHub.

### Frozen synthetic family holdout
| Metric | Train | Validation | NEW test (u_channel + web_bridge) |
| --- | ---: | ---: | ---: |
| Through+blind macro F1 | **0.9289** | **1.000** | **1.000** |
| Through recall | 60/60 | 12/12 | **12/12** |
| Blind recall | 52/60 | 12/12 | **12/12** |

New test confusion rows [other,through,blind] × predicted columns [other,through,blind]:
```
[[234,0,0],
 [0,12,0],
 [0,0,12]]
```
The **234 “other” are supervised FACES in 12 generator no-hole STEP parts**, not 234 independent parts. Positive CAD parts label only the intended cylindrical wall, and other positive-part faces are ignored. These are related *synthetic generator* families and NOT industrial CAD validation.

### Post-selection generalization probes: FAIL
After freezing the model, evaluated previously saved user-owned examples and 12 derived STEP variants of the newly held-out u_channel bore CAD **rotated 90° about X and translated (35,-27,15)**. No model changes or test-based tuning followed.

| Separate stress input | Actual label | Correct |
| --- | --- | ---: |
| Transformed u_channel through bores | through | **6/6** |
| Transformed u_channel blind bores | blind | **0/6** |
| Historical L_bracket (4 cylinder walls) | through | **3/4** |
| Identical bracket translated | through | **3/4** |
| Separate two-through-hole CAD (2 cylinders) | through | **1/2** |
| Separate one-blind-hole CAD (1 cylinder) | blind | **1/1** |
| Separate no-hole CAD | no cylinder | **0 cylinder predictions** |

The transformed examples are variations of already frozen test-family CAD, **not independent additional CAD families**. They are labeled **postfit robustness stress**, not counted as new independent test performance. The user's historical bracket labels are inferred from previously confirmed B-Rep through-hole geometry and are not an independently adjudicated industrial face dataset.

**This refutes any claim that synthetic 100% means solved model recognition.** Whole-assembly normalization moves the absolute face centroid, and the model still relies on orientation/position-sensitive features. Earlier inspected average normalized bore-wall Z is ~0 for simple plates vs -0.476 for L-support; this is a plausible shortcut, not proven causal feature attribution.

### Fail-closed automation
New `src/research/brepmfr_v2/readiness_gate.py` reads **research reports + exact model SHA**, checks family disjointness, score source, raw held-out confusion and rigid-pose per-class predictions; returns an explicit `rotation_stress_fail_blind_hole` blocker. Even if all synthetic and transform checks passed, it never certifies real-world production eligibility without separately labeled real industrial CAD. No private neural model or converter needs to be imported by this gate.

Local invocation (report/weights are user-owned and outside the Git repo):
```shell
python src/research/brepmfr_v2/readiness_gate.py --training-report "<LOCAL_FINAL_EVALUATION_JSON>" --stress-report "<LOCAL_POSTFIT_STRESS_JSON>" --checkpoint "<LOCAL_FROZEN_V2_MODEL_PT>"
```

### Next engineering decision
1. **Do not deploy** the new v2 checkpoint or replace epoch43; no trained ML can alter CAD dimensions, B-Rep geometry, FEA, 3D stress, saved evidence or optional AI conclusions.
2. Next separate experiment should make the inputs **rigid-pose invariant** (canonical local cylinder frame / intrinsic bore-cylinder geometry or balanced SO(3)/translation augmentation) while preserving reproducible same-converter data. Choose new previously untouched train/validation/test CAD families and freeze them before training—**do not tune on already viewed u_channel/web_bridge results**.
3. Require **independently labeled real industrial CAD samples** and separate through/blind precision, recall, F1 and failure coverage. Until then keep independent B-Rep topological hole evidence as the user-visible diagnostic, with conservative unknown for complex geometry.

**No user Windows install, original private epoch43, existing 26-file release manifest, UI, CAD, FEA, 3D or persistent records were changed.**
