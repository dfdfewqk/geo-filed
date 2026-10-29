# GeoField B07 — Automatic local R12 research fallback, never FEA truth

## Missing link corrected (repository code only)

Previously a new STEP with the per-import auto-ML checkbox enabled would
attempt **only** the legacy private BrepMFR worker. Its source and epoch43
checkpoint are intentionally absent from the signed GitHub source update.
When unavailable, the UI displayed a failed automatic ML status despite the
repository shipping a SHA-locked R12 research model that passed real
CadQuery/OCP + scikit-learn worker execution on Linux and Windows.

This patch connects **CAD analysis → opt-in automatic ML → fallback R12
research worker → same-CAD R12 result → evidence-gated UI/AI review**:

1. Existing default-on per-STEP toggle explicitly says BrepMFR with
   signed *local R12 research fallback*. Unchecking it disables both automatic
   model paths. R12 remains independently accessible via the existing
   manual research button.
2. A successful CAD job still first attempts the original BrepMFR preflight.
   Only if the private BrepMFR is unavailable and the user has opted in does
   `launch_automatic_r12()` check the original R12 model/manifest/Python
   environment. It copies **only a hash-bound temporary input** from the
   current STEP; rejects changed/stale CAD IDs, SHA mismatch, UUID collisions,
   preflight failures and duplicate/racing background tasks. No model weight
   is installed, copied or substituted.
3. `execute_r12()` is the same already-reviewed standalone R12 worker
   subprocess. The existing validation gate checks its research-only output,
   exact STEP SHA and current run ID; its results are never inserted into
   CAD B-Rep truth, FEA boundary/load inputs or mechanical safety rankings.
4. New `GET /api/ml/r12/latest/<current-cad-id>` returns **only the active
   CAD's** latest matching task; completed result is freshly checked through
   `r128_r12_status()` before a client receives it, and any contract
   mismatch is an evidence rejection. Old sessions are HTTP 409.
5. `watchAutoMl()` transfers to `watchAutoR12()` on explicit
   `r12_fallback` state. Both fallback and existing manual R12 button use the
   same SHA and strictly research-only guarded renderer; stale CAD
   generations cannot insert old predictions into the new CAD's view.
6. When R12 is also unavailable, the original CAD, FEA and report remain
   available and the research tab shows the exact optional unavailable
   state, without fake predictions.

## Independent evidence and limitations

PR #45 already validated **the real bundled R12 joblib** on native Linux
and Windows CI workers and its output through the production AI agent,
but that was not an actual user Windows installation. This PR's new
`test_auto_r12_fallback.py` uses real production launcher functions
against disposable synthetic STEP files, fake **worker scheduling** (not
mock model output); it proves optional/opt-out, dedup, SHA, file ownership,
thread failure and CAD/FEA immutability. The new frontend JS test runs
the actual production watcher/renderer under a simulated DOM with
specially crafted good/invalid research JSON and stale-CAD responses.

Real user Windows STEP→R12 automatic inference and presentation is
**not yet observed**. BrepMFR's private worker, epoch43 model and
through/blind-hole classification quality remain unverified. This is
NOT a new model, not FEA surrogate stress prediction, not paid API
integration and not a structural safety assessment.

## Closure

This allows existing GitHub-provided research ML to be *connected in
application logic* without Antigravity. The sole remaining physical
Windows step is a single integrated acceptance with the user's
installed Python/DLLs and user-owned STEP after a one-shot source
inventory and local preflight. If it fails, bring the actual sanitized
status/log to ChatGPT for a source-only fix.
