# GeoField B01 — one-time installed runtime inspection (2026-10-28)

**Purpose:** Identify missing, mismatched and unverified installed Python modules before
Antigravity B02–B06 changes the Windows app. This **does not** run GeoField,
perform FEA/ML, install files, extract personal STEP/FRD/SQLite/model files, or
upload anything. B07 is the **only** planned user-assisted Windows full test.

## What is already verified in GitHub
- Backend canonical branch: `work/geofield-ab-ai-c3d10-integration-20261026`.
- Original Windows installed module source such as `history_store.py`,
  `fea_restore.py`, `integrated_results.py`, `fea_engine_worker.py`,
  `engine_runtime.py` **is not fully present in GitHub**. Never fabricate
  replacements or silently overwrite the user's own installed code.
- New A11 Python helpers `fea_history_a03.py`,
  `fea_history_delete_a04.py`, `fea_field_a06.py`,
  `fea_report_a08.py` **are present only in tracked GitHub source**.
  These are staging requirements for B06, not legacy private files.
- Existing `runtime_preflight.py` statically checks old required filenames,
  engine API and imported function names. B01's new
  `runtime_inventory_b01.py` adds only **size, SHA-256, safe literal version,
  missing/invalid/mismatched-source status** with no raw source export.

## Antigravity B01 automatic run on the user's PC (no manual game/app test)
1. Use an up-to-date checkout of the canonical GitHub branch in a local
   development folder, not the live installed runtime. Locate the user's actual
   installation (default from legacy config:
   `%LOCALAPPDATA%\GeoFieldCAD\onefile_runtime\8a9ac53a821a0eb5`).
   Do not assume the default path exists or is the installed version.
2. From the checked-out repository directory, run from a normal unprivileged
   shell, without starting or stopping the installed application:
   ```powershell
   py -3 src/runtime_inventory_b01.py --runtime "$env:LOCALAPPDATA\GeoFieldCAD\onefile_runtime\8a9ac53a821a0eb5" --candidate src/payload --source-root src
   ```
   This prints JSON to stdout and **writes no files** by default.
3. If B01 needs a report file, optionally run the same command with
   `--output "$env:USERPROFILE\Downloads\GeoField_B01_Inventory.json"`.
   Output creation is exclusive, never overwrites an existing JSON, and is
   refused inside the runtime directory.
4. Inspect `missing`, `invalid_or_unsafe`, per-module `sha256`,
   `literal_version_unverified`, `engine_runtime_static_api`,
   `backend_import_static_api`, and
   `new_github_helpers_not_expected_in_old_runtime`. Record whether the
   installed source is genuinely available, identify its version/expected
   exports, and check the installation location/identifier if different.
5. Share **only the JSON summary if authorized**, never a ZIP of private
   runtime Python sources into a public GitHub repository. Hashes are local
   fingerprints, **not authenticity or import-success proof**. If an actual
   module is missing, ask for the verified original from its legitimate
   installation source, and block B06 installation until resolved.

## Interpretation of B01 result
- `static_source_inventory_complete=true`: all **old required files** in the
  fixed allowlist are readable Python or stylesheet bytes. **Does not** mean
  Python imports, FreeCAD, CAD topology, Gmsh, CalculiX, DeepSeek or rendering
  work, nor that the installation can be upgraded.
- `backend_import_static_api.compatible=true`: the checked-out new backend's
  **direct import symbols** appear statically in inspected old modules. This is
  not runtime signature, ABI or binary DLL validation.
- `source_authenticity_proven=false`, `safe_to_install_inferred=false`,
  `installed_app_operational=null`: these are intentionally never claimed
  by the B01 inventory.
- `new_github_helpers_not_expected_in_old_runtime` is a separate source
  staging inventory; do **not** add these to `EXISTING_REQUIRED` and wrongly
  block validation of the older installation.
- Errors, missing runtime, symlinks, altered files and missing API functions
  are explicitly reported instead of making fake source stubs.

## B01 deliverable and stop boundary
Deliver the local JSON fingerprint inventory + exact installed module/version/
API mismatch findings to the B02 owner; do not mutate installed files. If the
runtime has not yet been inspected on the real PC, B01 is **code/CI prepared,
but actual Windows source inventory pending**, not physically complete.
The original private source review ZIP helper is still optional for
authorized **local-only** recovery, not a prerequisite for this JSON inventory
and never auto-generated here. No user-assisted physical test until B07.
