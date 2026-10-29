# B07 — BrepMFR optional dependency and archived edge-input research

**Date:** 2026-10-29. Source update applies to canonical integration branch `work/geofield-ab-ai-c3d10-integration-20261026`.

## Confirmed code defect and correction

The production `GeoField_CAD_Analysis.py` claimed BrepMFR was optional but imported `KNOWN_CKPT` directly from `ml.brepmfr_worker` at module import time. GitHub's 26-file package does not contain this private worker. Independently, `runtime_preflight.py` declared that same optional worker as mandatory. An installed CAD/FEA runtime otherwise containing all core dependencies could therefore fail to start or be blocked before update solely because its research-only ML worker is absent.

The corrected backend uses **the pinned known research checkpoint SHA-256** `50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1`, also used by the existing read-only ML source reviewer. This is a reference hash only; **it is not a substituted model or evidence the model exists**. Original `ml_preflight()` still requires the private worker, preprocessing code and checkpoint plus Python libraries. `execute_ml()` still rejects mismatched model and STEP hashes. The read-only installed-runtime audit now separates `OPTIONAL_RUNTIME_MODULES` from its core `EXISTING_REQUIRED` list. Missing worker reports *optional missing*, not *CAD/FEA unsafe*. Other missing mandatory modules remain blocked.

No BrepMFR source, model checkpoint, SQLite, STEP, FEA input or FRD is fabricated or added to the normal 26-file update.

## Recovered research code and independent geometry-only replay

An existing privately stored 2026-10-20 BrepMFR edge-preprocessing research archive contains a candidate `ocp_step_to_graph.py`, baseline source, MIT license and support modules. Separately saved `GeoField_ML_R12_Hole_Classification_Fix_Tested_20261020.zip` contains a suitable *synthetic* 11-face test STEP.

The archived preprocessing paths were run again under the development container's **actual OCP + numpy** without a model checkpoint:

| Same synthetic through-bore STEP | Baseline | Typed-edge candidate |
| --- | ---: | ---: |
| Directional edge samples | 540 | 540 |
| Nonzero valid tangent samples | 0 | **540** |
| Shapes and outputs | Same STEP | 11 faces, 54 directional edges; all edge/face arrays finite |

Root defect: `FindKey()` returned generic `TopoDS_Shape`, while `BRepAdaptor_Curve` requires `TopoDS_Edge`. Candidate uses `topods.Edge_s(...)` and fails closed when all tangent features are fabricated zeroes. Original archived research reports model test showed through-hole/blind-hole classification errors **remain** even after tangent correction. **No checkpoint was available for fresh model re-inference during this review, so do not claim ML model accuracy or real user's Windows prediction.** No archived candidate source was silently written into the installed runtime or the GitHub 26-file update.

## Next non-GitHub dependency

Use the existing `GeoField_ML_Source_Review.cmd` once on the actual Windows installation. Its private local ZIP must be inspected for secrets/license before sharing. Specifically determine whether `ml/brepmfr_worker.py` and `ml/brepmfr_core/ocp_step_to_graph.py` exist, and whether the on-disk source is the archived baseline, the known 2026-10-20 research correction, or another version. Then safely reconcile source-by-source with exact SHA and backups, without replacing unrecognized files or model weights. A new real Windows BrepMFR classification run and CAD→ML→AI GUI evidence are still required before calling GeoField ML integrated.

**Closure status: optional import startup/installation blocker fixed in GitHub; BrepMFR research model integration/quality NOT closed.**
