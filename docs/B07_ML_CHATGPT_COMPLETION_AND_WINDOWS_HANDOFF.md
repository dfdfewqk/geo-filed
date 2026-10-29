# GeoField B07 — ChatGPT-side ML completion and single Windows handoff

## Grounded state, 2026-10-29

- Integration branch: `work/geofield-ab-ai-c3d10-integration-20261026`.
- CAD/STEP, Windows CalculiX FEA and 3D visualization were visually observed in the user's earlier screen recording. The A08 report label defects were corrected in PR #44.
- The **actual bundled R12 research checkpoint** was exercised against CadQuery-generated STEP on **real Windows and Linux Python ML environments** in PR #45, including SHA-256 provenance, synthetic through-bore/no-bore geometry, subprocess worker and production response-validation gate. This is **not** proof that the user's installed R12 environment is available or that the model is accurate on industry STEP.
- BrepMFR runs in the installed private runtime, not this 26-file source update. `ml/brepmfr_worker.py`, `ml/brepmfr_core/compare_preprocessing.py` and the epoch43 `best-epoch43-f1_0.8626.ckpt` are not in the GitHub repository and must not be invented. The previously saved ML investigation reported incorrect edge-grid samples and persistent through-hole vs blind-hole misclassification; the candidate fix was NOT installed into the actual user runtime.

## Code completed locally in GitHub

1. `ml_preflight()` now checks the **required BrepMFR worker, preprocessing source and original checkpoint SHA-256 before attempting up to 55 seconds of Python dependency probing** (PR #45); status checks no longer perform duplicate ML probes.
2. The R12 `ml_r12_bridge.preflight()` checks required source, research model hash and research-only manifest **before** importing/locating a Python ML environment; missing assets fail quickly and visibly rather than delaying the CAD screen. The actual R12 model worker is unchanged.
3. `GeoField_ML_Source_Review.cmd` and `ml_runtime_source_review.py` are standalone, read-only, stdlib-only helpers in the SHA-256-locked Windows update candidate folder. They locate the existing runtime and generate a **LOCAL PRIVATE ZIP** inside Downloads. The ZIP contains only bounded `ml/brepmfr_worker.py` and `ml/brepmfr_core/**/*.py` Python sources and a manifest; a legacy epoch43 checkpoint is hashed but NEVER put in the ZIP. No STEP, SQLite, CalculiX, passwords, .env or unselected modules are deliberately collected. No source is executed or installed. Private code may contain sensitive paths/secrets: **the owner must inspect the ZIP before sharing it anywhere**. CLI accepts `--runtime` and `--output` for nondefault installs.
4. Tests exercise missing/unsafe/symlink sources, malicious non-Python code, 2 MB per-source cap, no checkpoint/data leakage, rejected overwrite, negative and valid ML preflight, Linux/Windows R12 model subprocess and the unchanged 26-file signed update manifest.
5. The package remains a **source update candidate, not a full offline EXE**. No model weights, user CAD or raw solver data are bundled.

## Only remaining Antigravity / physical Windows work — one inventory, one acceptance

**First, read-only local inventory only:** in the newest extracted Windows candidate folder run `GeoField_ML_Source_Review.cmd` once. It writes `%USERPROFILE%\\Downloads\\GeoField_ML_Source_Review_*.zip`. After reviewing it for sensitive code, optionally send only the review source ZIP back to ChatGPT (not to public GitHub). If the ZIP is incomplete, inspect its `review_manifest.json` to see the exact missing worker or preprocessing file. For private model/checkpoint the SHA status is enough; **do not send the .ckpt**. Have Antigravity record import outcomes for the already installed ML Python (torch, numpy, cadquery, OCP, sklearn, joblib) with exact error only; no pip installs, training, dependencies, secrets or code edits in this step.

**ChatGPT then:** inspect obtained original BrepMFR code, implement bounded preprocessing/worker fixes, add automated real-source/no-false-evidence regression coverage, prepare signed update safely without changing ML weights. Missing source and an unknown checkpoint remain hard blockers. Refuse unsafe shortcuts.

**Finally, one physical Windows acceptance:** on the actual installed version, use one real STEP to verify CAD→BrepMFR/R12 inference status→screen and reference-only AI pipeline; only if needed repeat a FEA display/HTML report check using an already verified run. Record actual errors and URLs/status with no credentials. No repeated Gmsh/CalculiX solve is required solely to test ML. Never claim structural safety or industrial accuracy from the research classifiers.

## Exact closure criteria

- **R12 repo-side actual model subprocess and model validation:** completed.
- **BrepMFR private-source/weight inventory and Windows inference:** pending real Windows data.
- **BrepMFR reliable classification accuracy:** NOT established; keep label explicitly research-only.
- **User Windows R12/BrepMFR status and same-CAD provenance in UI/AI:** pending Windows evidence.
- **ML prediction driving/altering FEA inputs:** deliberately disabled; this is not an unchecked feature to add during integration.
- **Final full GeoField Windows acceptance:** remains open until above runtime evidence is reviewed.

Do not re-open completed B03/B04/CAD rendering merely to claim a complete FEA retest; that was visually demonstrated already. Do not add new ML architecture, model training or paid AI calls while closing this backlog.
