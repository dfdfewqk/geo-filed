# GeoField B07 — BrepMFR-v2 NEW research model preparation (2026-10-29)

## Outcome and design boundary
The epoch43 legacy checkpoint cannot be fixed safely by feature-slot patches, and the genuine original training forward remains undocumented. This change builds a **new, isolated research corpus and optional small graph-neural training baseline** rather than overwriting the 27-class epoch43 model.

- Existing training geometry generator: `src/payload/ml/r12_research/build_data.py`. It already creates parameterized CAD with original **generator-intent** labels and splits entire **geometry families**, not random face rows.
- New research-only builder: `src/research/brepmfr_v2/prepare_corpus.py`.
- New train/holdout evaluator: `src/research/brepmfr_v2/train_research.py`.
- The exact private 2026-10-15 OCP STEP converter is **read from a separately held, user-selected local source** and is allowed only when SHA-256 equals `6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46`. It is never bundled, uploaded, modified or substituted with the public converter. A different Windows-installed converter hash is **not automatically accepted**. Train and future inference must use this identical exact converter version.
- New research model has **three outputs**: `other`, `through_hole`, `blind_hole`. It is a new small CNN-over-face-UV + graph-neighbor + edge-feature head; **not** the public 27-class BrepFormer and **not** drop-in replacement of epoch43.
- A hole STEP labels ONLY the generator-defined cylindrical wall, with other faces marked `-1` ignored, while a generator `no_hole` CAD gives negative `other` supervision to all its faces. This minimizes bogus feature labels but means evaluations **do not measure every face in a positive CAD**.
- Face-level mapping is not assumed from a model prediction. Reimported face B-Rep order is compared to graph order using **surface type + identical normalized area scale + centroid global transform**, and the intended hole is matched by **unique axis line position and radius** from the original CAD generator parameters. Fail closed if order or target cannot be proved.
- STEP and graph SHA-256 checked, copied graph arrays validated for finite values/shapes, no symlink/traversal/duplicate content, no family or source-label leakage. Checkpoint is a new versioned research `.pt` file under an explicitly new user-chosen output folder; all outputs carry `eligible_for_production=false`.
- Validation determines the selected epoch; held-out test is run **once only after** this choice. Score table includes per-class precision, recall, F1 and confusion matrix. These are **synthetic family holdouts only**, not industrial CAD performance certification.

## Real user-owned STEP evidence (isolated local research runtime)
The existing `GeoField_ML_R12_Hole_Classification_Fix_Tested_20261020.zip` includes 108 generated, labeled STEP files. An **independent OCP test** re-read the 108 real STEP bytes and ran the exact archived converter, checked the original STEP SHA-256s, normalized face-type/area/centroid alignment and unique generator-intent bore wall mapping:

| Family split | STEP files inspected | Result |
| --- | ---: | --- |
| Train: plate, rounded_plate, notched_plate | 54 | 54/54 accepted |
| Validation: raised_edge | 18 | 18/18 accepted |
| Test: l_support, chamfer_plate | 36 | 36/36 accepted |
| **Total** | **108** | **108/108 mapped** |

Design labels: 36 `through_hole`, 36 `blind_hole`, 36 `no_hole`. **0 SHA/type/area/centroid/unique-target failures**. The verification used research binaries privately and did **not** modify any user runtime or release file.

This is proof that the original generator and pinned converter **can be aligned on these 108 STEP designs**. It is **not** a trained model score and cannot be generalized to 27-class CAD face truth or industrial STEP. A separate graph-corpus builder and train script are now available for opt-in local execution; synthetic model quality must still be measured and checked before any possible promotion.

## Example research-only commands (not a production installation)
The caller must own the existing private converter and choose local workspace paths. Do NOT run inside the installed `onefile_runtime` folder.

```powershell
# 1) Create a fresh synthetic dataset from the already tracked R12 generator
python -m ml.r12_research.build_data --out "D:\\GeoFieldResearch\\r12_dataset" --n 6
# 2) Build graph NPZs from the SAME, SHA-pinned OCP converter
python src/research/brepmfr_v2/prepare_corpus.py --dataset "D:\\GeoFieldResearch\\r12_dataset" --converter "<EXACT_PRIVATE_OCP_CONVERTER.py>" --out "D:\\GeoFieldResearch\\graphs_v2"
# 3) Train separate opt-in research checkpoint; no automatic model install
python src/research/brepmfr_v2/train_research.py --corpus "D:\\GeoFieldResearch\\graphs_v2" --out "D:\\GeoFieldResearch\\model_v2" --epochs 20
```

Dependencies: explicit Python environment with CadQuery/OCP, NumPy and PyTorch (local). The R12 generator requires the GeoField payload on Python's module path. The commands produce standalone research results and do not call DeepSeek or any external service.

## Inference integration gate (NOT yet passed)
Before a new model can replace user-facing BrepMFR research predictions, implement an isolated inference worker that loads its trusted **new model SHA** with PyTorch `weights_only=True`, verifies the **exact same converter SHA**, correctly binds every graph-face ordinal to the current CAD STEP and schema, compares class metrics on an **independently held-out real CAD family**, exposes abstention for low-confidence/complex cases, and keeps all predictions separate from FEA/AI engineering evidence. The current `ml/brepmfr_worker.py` and epoch43 checkpoint must remain untouched.

**No 27-class BrepMFR model, no actual Windows installation, no industrial accuracy validation or full application release is claimed by this step.**
