# GeoField B07 BrepMFR-v2 — first actual training and held-out evaluation (2026-10-29)

## Status: TRAINED locally, NOT ACCEPTED for production
Research-only 3-class model was trained on the owner's previously generated STEP dataset using the exact archived OCP converter SHA `6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46`. This **does not train or improve the old 27-class epoch43 BrepMFR model**. No original STEP/weights, installed Windows runtime, FEA or user data were changed or committed.

The actual run used an isolated Linux NumPy/OCP/PyTorch environment, **local runner implementing the same CNN+neighbor+edge architecture, features, AdamW and validation-selected early-stop logic** as `src/research/brepmfr_v2/train_research.py`. The report below is from this actual local runner; it is **not** being presented as a full GitHub Actions execution of the private converter or as a certified production benchmark. Complete original source and per-case data remain private.

| Split | CAD geometry families | STEP designs | Bore classes | Evaluation use |
| --- | --- | ---: | --- | --- |
| Train | plate, rounded_plate, notched_plate | 54 | 18 each through / blind / no-hole | Optimizer updates |
| Validation | raised_edge | 18 | 6 each | Epoch selection only |
| Test | l_support, chamfer_plate | 36 | 12 each | Evaluated after selecting epoch |
| **Total** | **Six nonoverlapping families** | **108** | **36 each** | Synthetic generator intent |

Actual graph conversion and independent face-order/axis/radius mapping: **108/108 accepted**. STEP input SHA, graph array sizes and finite values also checked. New model seed `20261029`, PyTorch AdamW lr `0.001`, CNN UV face grid + face/neighbor/edge attributes, `20` maximum epochs, early stopping after 8 epochs without improvement, sqrt-inverse-frequency weights for only explicitly labeled faces. Train label counts: `other=156, through=18, blind=18`. A hole STEP labels **only** its unique designed cylindrical wall; other faces are **ignored**, so `other` support does not measure other faces inside a positive CAD with holes.

## Actual selected-epoch results

The best validation macro F1 was **1.000 at epoch 2**. Training stopped at epoch 10 on the predefined patience rule. The selected epoch-2 weights were then evaluated on the held-out families.

| Metric | Validation: raised_edge | Test: l_support + chamfer_plate |
| --- | ---: | ---: |
| Macro F1 (other+through+blind) | **1.0000** | **0.6816** |
| Other precision / recall / F1 | 1.000 / 1.000 / 1.000 | **0.9391 / 1.000 / 0.9686** |
| Through precision / recall / F1 | 1.000 / 1.000 / 1.000 | **0.5556 / 0.4167 / 0.4762** |
| Blind precision / recall / F1 | 1.000 / 1.000 / 1.000 | **0.7500 / 0.5000 / 0.6000** |
| Through+blind macro F1 | 1.000 | **0.5381** |

Held-out confusion matrix, rows=actual [other,through,blind], columns=predicted [other,through,blind]:
```
[[108, 0, 0],
 [  5, 5, 2],
 [  2, 4, 6]]
```
**Do not call 108 true-negative CAD models**: `other=108` counts individually supervised faces on 12 no-hole CAD models, not 108 independent parts.

### Failure concentrated in new CAD families
| Held-out geometry family | Through recall | Blind recall | Bore-intent STEP count |
| --- | ---: | ---: | ---: |
| l_support | **1/6 = 16.67%** | **0/6 = 0%** | 12 |
| chamfer_plate | **4/6 = 66.67%** | **6/6 = 100%** | 12 |

This validation-test collapse is material. The reported validation F1=1.0 on one single CAD family **does not establish a generalizable neural model**.

## Additional external owned STEP diagnostic (NOT a second tuning set)
The same fixed checkpoint was run on five extra owner-owned CAD files already available from the research archive:
- `two_through_holes.step`: one cylinder predicted `other`, one `through` with uncalibrated top score ~0.395.
- `one_blind_hole.step`: one `blind` (uncalibrated score ~0.370).
- `plain_solid.step`: no cylindrical faces, all six predicted `other`.
- Historical L-bracket and its translated copy: **all four actual cylindrical wall faces predicted `other`**, including scores above 0.82. High softmax output **is not calibrated confidence** and does not justify automatic use.

These examples are intentionally recorded as **negative product readiness evidence**, not additional held-out accuracy statistics.

## Decisions
1. New research checkpoint is **not eligible for production** (`eligible_for_production=false`); never replace epoch43 or forward to FEA/AI/structural safety.
2. Keep the already merged independent conservative B-Rep solid-occupancy through/blind/unknown display; it is a geometric diagnostic, not evidence of better ML.
3. Current research evaluator has been enhanced to emit **hole-only macro F1 and per-family confusion/recall from the same evaluation pass** so its "other" class cannot mask generalization failures.
4. Before a new training experiment, broaden TRAIN and VAL geometry families and collect independently labeled industrial STEP variants. Do not change model choices based on this already-consulted test split; reserve a fresh external family holdout for any future revised model.
5. The available local 33KB `.pt` research checkpoint is kept in the sandbox, deliberately **not** auto-integrated or uploaded to GitHub as a verified product model.

This step **finishes the first real training/evaluation run**, but does **not** solve neural through-hole or blind-hole recognition across unfamiliar CAD families.
