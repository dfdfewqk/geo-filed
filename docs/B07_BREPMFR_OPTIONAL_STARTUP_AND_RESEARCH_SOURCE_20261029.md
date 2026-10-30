# GeoField B07 — optional BrepMFR startup blocker and historical research-source check

## Actual blocking defect corrected

The production backend at `src/payload/GeoField_CAD_Analysis.py` used to execute
`from ml.brepmfr_worker import KNOWN_CKPT as BREPMFR_SHA256` **at module import time**.
The BrepMFR worker is intentionally **not** included in GitHub's 26-file signed
Windows source candidate (legacy Windows private runtime prerequisite). If the
worker was missing or its optional PyTorch import failed, CAD/FEA backend startup
would fail before its own optional `ml_preflight()` could safely report an unavailable
research model. This violated the design goal that optional ML failures must
not make otherwise valid CAD/FEA fail.

The fix pins the known, previously independently recorded epoch43 SHA-256
`50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1`
as a core constant without importing or executing third-party/private ML code.
The same digest is already declared in the read-only
`src/ml_runtime_source_review.py` file. Real `execute_ml()` still launches
the worker **only** on an actual opted-in inference with a verified checkpoint,
and checks the exact checkpoint and STEP hashes before and after the call.
`/api/ml/preflight` still requires the worker, preprocessing source, pinned
checkpoint digest and Python dependency resolution. No fabricated weights,
empty model, skipped integrity check or automatic AI call.

## Previously saved user-owned research artifacts re-examined

Existing user Library source archives from **2026-10-20** were inspected
read-only in a separate temporary tool workspace; they are NOT being
silently pushed into the public GitHub source tree or installed over a
legacy Windows runtime.

- `GeoField_BrepMFR_Edge_Extraction_Fix_Research_20261020.zip`
  holds `candidate_source/ml/brepmfr_core/ocp_step_to_graph.py`,
  `compare_preprocessing.py`, original baseline and regression evidence.
  The distributed upstream license is MIT (license retained in archive).
- `GeoField_ML_Edge_Input_BugFix_Checked.zip` contains a newer verified
  `ocp_step_to_graph.py`, its diff and report; file SHA-256
  `54d1db09193c133e02ae7060ca103b374620e3c10275a99f5626051b26b018e2`.
- `GeoField_ML_R12_Hole_Classification_Fix_Tested_20261020.zip`
  includes the actual old L-bracket STEP geometry and 3 generated example STEP
  files, plus the **separate R12** model. R12 is not a BrepMFR checkpoint.

Independent OCP 7.9.3.1 / CadQuery 2.8 / NumPy 2.3.5
source-only preprocessing execution in the review environment,
without any BrepMFR epoch43 checkpoint:

| real STEP example | verified nonzero tangent samples |
| --- | ---: |
| plain_solid.step | 240 / 240 |
| two_through_holes.step | 360 / 360 |
| one_blind_hole.step | 300 / 300 |
| L_bracket_shifted_100_200_300.step | 600 / 600 |

The original L-bracket STEP had SHA-256
`fe65841074c5fc6bd74442b147e5688490ec1ad79d5fb1e41bdccd3514bccf32`;
the corresponding translated clone preserved face/edge counts and normalized
input features to max absolute diffs: face grid ~5.96e-7, face attributes
~2.27e-7, edge grid ~2.70e-6, edge attributes 0. This independently
confirms the historical *graph extraction* repair functions with real
STEP files. It does NOT confirm the old checkpoint can classify holes
reliably or that it is installed on the current Windows PC.

The previous 2026-10-20 regression report explicitly recorded false
`blind_hole` predictions on two through-holes even with fixed edge
features. **Never promote BrepMFR class predictions to verified B-Rep
geometry or structural FEA facts.**

## Actual remaining B07 requirement

The original installed `ml/brepmfr_worker.py`, epoch43 checkpoint and
`ml/brepmfr_core/` provenance are **not present in tracked GitHub
payloads**. The recovered research converter is not an automatic update
for these unknown private Windows files. Do not overwrite a user's
installed converter without matching its exact original hash and creating
a checksum-verified backup. The actual worker's imports and model
architecture must be inspected before a safe integration can be
proven. Use the existing `GeoField_ML_Source_Review.cmd` private
inventory; checkpoint fingerprint only, never upload/copy the weight.

Final actual Windows BrepMFR→ML UI→AI evidence acceptance and model
classification quality remain pending, separately from the repaired
CAD/FEA core startup. No user-installed files were changed.

## 2026-10-29 archived worker runtime-import completeness gate

An actual mismatch was found in `ml_preflight()`: it verified the **top-level**
`brepmfr_worker.py` and `compare_preprocessing.py`, pinned checkpoint and
`torch/numpy/OCP` imports, but did **not** verify multiple local modules
required by the recovered Oct-15 worker, such as `legacy_architecture.py`,
`ocp_step_to_graph_baseline.py`, `minimal_src/brepformer/data/collator.py`,
and its graph/attention layers. A partially copied legacy research environment
could therefore advertise `available` despite a guaranteed worker import error.

The new read-only `brepmfr_source_preflight()` fingerprints the **small worker**
using SHA-256 `42975e1b95f87106643b8e68c6e2c176403e717978a4f76ebe780b2375b2a89d`.
Only when this exact archived source matches, it checks the expected Python
import-tree file presence and rejects symbolic links, before starting a
Python dependency probe. Different worker hashes yield
`other_worker_version_not_verified` rather than being misidentified as the
archived worker. File presence alone does **not** validate native dependencies,
model accuracy, or Windows end-to-end runtime. No original worker source or
checkpoint enters GitHub or is rewritten.
