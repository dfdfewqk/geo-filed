# GeoField integrated code audit — 2026-10-29

## Purpose and scope

Audit the current **actual integration branch**, not only a single screenshot error. Review GitHub-tracked Python/JS, deployment candidate installation/rollback and available CI evidence. This is **not** an assertion that private Windows runtime modules, the user's checkpoint or their local actual ML/FEA environment were available in GitHub.

### Inspected integrated subsystems

| Area | Code locations / validation | Outcome |
|---|---|---|
| Candidate install and rollback | `installer.py`, `bootstrap.py`, `runtime_compatibility.py`, `build_integration_candidate.py`, Windows upgrade CI | Exact SHA checks and backed-up unknown local updates preserved; private legacy runtime still required |
| CAD import and active STEP binding | `GeoField_CAD_Analysis.py` handler / process_job, `cad.js` import-generation guards | **Fixed interrupted network upload leaving a partial STEP copy**; exclusive creation now rejects UUID collisions without deleting someone else's bytes |
| Optional ML dependency readiness | `ml_preflight`, `capabilities`, `ml_r12_bridge`, `ml_env_resolver` | **Fixed status repeatedly reading an entire large BrepMFR checkpoint**; short metadata-keyed checkpoint hash cache, and unreadable / symlink / oversized checkpoint fail closed without taking the CAD status API down |
| Backend startup / Windows installer | `bootstrap.py --check` 35-second timeout vs optional `resolve_ml_python` 55-second deadline | **Fixed essential startup calling optional ML discovery**. Core `--check`, server readiness and `/api/status` now do NOT run the optional ML import probe; users can explicitly verify with `/api/ml/preflight` |
| R12 real model/AI | `ml_r12_bridge.py`, real checkpoint/STEP worker CI, `gf_agent_evaluate` | No new model training; real Windows/Linux R12 research-only tests remain, failed or unverifiable model inputs cannot change FEA |
| FEA / FRD / 3D / reports | `fea_solver.py`, field and provenance gates, histories, `fea_report_a08.py` and existing tests | No ungrounded engineering-value modifications. Previously recorded Windows FEA/3D success remains; final user-installed ML integration still pending |
| Records, deletion & rollback | `fea_history_a03.py`, `fea_history_delete_a04.py`, SQLite + Windows CI | No destructive migration or SQL rewrite; original user datasets untouched |
| UI state races | `frontend/cad.js` generation tokens/active CAD guards, JS regression tests | No new frontend architecture/rewrite; existing race tests included in full A11 run |

### Debug findings/fixes

1. **Periodic checkpoint hashing on status requests.** Prior `capabilities()` called `ml_preflight()` on each status request. If the private BrepMFR checkpoint exists, it repeatedly hashed all its bytes. The patched explicit `ml_preflight()` caches only a 30-second *status-display* verdict keyed by pathname, size, mtime and inode; never caches a result to authorize ML execution. `execute_ml()` still verifies STEP+checkpoint SHA **before and after** each worker invocation. A file that is unreadable, linked, or larger than 2GB is rejected without running optional ML or breaking CAD/FEA status. Even if metadata could be spoofed, execution never trusts the cached verdict.
2. **Optional ML probe could exceed installer startup deadline.** The 55-second ML resolver was invoked by core `capabilities()` during `GeoField_CAD_Analysis.py --check` while bootstrap's updated-backend readiness check has a 35-second timeout. Fixed by using `capabilities(..., probe_ml=False)` in core readiness/status; this returns `ml_probe_state=not_checked_optional` and does not pretend an unprobed ML model is operational. Explicit `/api/ml/preflight` still verifies original source, model hash, Python imports before any actual inference. No FEA or CAD execution logic changed.
3. **Partial STEP upload cleanup.** Prior `receive_step()` opened a new UUID path with `wb` and did not remove a partly written file when the client disconnects mid-upload. Updated to exclusive `xb`, tracks whether this request created it, deletes only that owned partial file on failure, leaves an existing UUID-collision file intact, and preserves successful upload for the established asynchronous CAD worker. Does not remove user's original STEP.

### Regression tests

- `test_ml_preflight_fast_path.py`: real production `ml_preflight/capabilities` AST functions: absent, invalid, unreadable, symlink or oversized checkpoint, repeated status without repeated hash, explicit ML probe, optional probe skipped in startup.
- `test_cad_upload_stream_cleanup.py`: actual `Handler.receive_step` AST method against synthetic in-memory client stream: interrupted upload cleanup, UUID collision non-overwrite, invalid STEP header cleanup, valid job launch.
- Linux `pytest` all GitHub-runnable tests, frontend Node `test_*.js`, Windows disposable install/runtime/source identity and R12 actual model CI.
- Never call real paid APIs or modify original STEP/FEA/checkpoint/SQLite as part of the tests.

### Pending separate Windows acceptance

The user's actual BrepMFR source/checkpoint+Python versions are missing from GitHub; its preprocessing classification reliability cannot be certified by repository-only tests. Use the local read-only `GeoField_ML_Source_Review.cmd` and private inventory, inspect for sensitive paths before sharing, then review original source and verify one actual Windows ML/AI result. The remaining B07 acceptance stays open. Do not report that this code audit alone makes the whole GeoField application final/production ready.
