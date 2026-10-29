# B07 – Core status ML false-negative and one-shot local readiness

## Problem found after PR #49/#50

The core CAD/FEA startup intentionally skips a potentially 55-second optional
BrepMFR Python import probe. The local `/api/status.capabilities` now marks
`ml_probe_state=not_checked_optional`, with `ml_inference=false` as a
**non-assertive placeholder**. The existing `src/acceptance_probe.py`
incorrectly interpreted this placeholder with
`bool(capabilities.get("ml_inference"))`, recording that ML was unavailable
even though it had never been checked.

## Corrected observation contract

- Default `GeoField_Acceptance_Check.cmd` remains fast and read-only:
  `ml_environment_reported_available=null`,
  `ml_probe_state=not_checked_optional`, no optional ML probes.
- The new `GeoField_ML_Environment_Check.cmd` verifies the complete signed
  Windows candidate and calls
  `acceptance_probe.py --check-ml-env` **once**. It only performs local
  same-origin GET calls to `/api/ml/preflight` and
  `/api/ml/r12/preflight` with up to 70-second timeouts for optional
  dependency discovery. No worker execution, STEP upload, checkpoint
  replacement, paid LLM request, FEA solve, or file deletion.
- The report distinguishes `brepmfr_environment` and `r12_environment`
  separately: `not_checked`, `ready_for_research_inference_not_executed`,
  `unavailable_or_untrusted`, `invalid_local_preflight_contract`, or
  `local_preflight_unreachable`. The combined optional environment flag
  is true only if at least one signed research preflight actually reported
  its exact mode and available=true.
- Actual user-PC inference is still
  `ml_user_windows_inference=NOT_TESTED_BY_THIS_PROBE` independently of
  preflight success.
- The status report deliberately strips Python paths, API errors, input STEP
  filenames, CAD UUID and SHA, model weights and keys. Only error **type**
  and internal phase label are recorded.
- The `acceptance_probe.py` process exit code also reflects CAD/FEA
  acceptance. Its nonzero result is **not** equivalent to ML unreadiness:
  read the two explicit ML environment labels in the sanitized JSON.

## Regression

Production acceptance-probe tests assert that skipped status is never
misrepresented, explicit BrepMFR-unavailable/R12-ready reports correctly,
malformed/offline model preflight never promotes a model to usable, and
sensitive local Python paths and credentials are not copied to reports.
Both new helper files are included in the manifest-verified top-level
Windows source update folder. No standalone EXE or private BrepMFR weight
is embedded.

Remaining B07: authenticated existing Windows local source/weight/Python
environment, real STEP BrepMFR classification, same-CAD UI/AI evidence and
classification-quality review; GitHub CI cannot establish those by itself.
