# B07 Windows local preflight recheck — blocked B06 candidate

## Observed failure (2026-10-28 user screenshot)

The **26-file package integrity verification succeeded**; `GeoField_Start.cmd` then refused local source migration at **`[STEP 1/5] Verify all package files and SHA-256 hashes`**, before releasing port 8600, installing code or opening the backend. It reported exit code **25** with many `MISMATCH FILES`. This is **not evidence** of a Gmsh/CalculiX/3D runtime failure; no FEA execution was attempted.

The displayed screen cannot tell whether a particular file was *missing*, *unrecognized existing local code*, *unsafe symlink* or *unreadable*. Do **not** assume they are all missing or all updatable. Existing file-specific statuses are recorded read-only at
`%LOCALAPPDATA%\GeoFieldCAD\diagnostics\r12_launcher\geofield_version_compatibility.json`
under `file_versions`. That JSON also includes source API availability and runtime dependency summaries, not CAD/FEA/SQLite contents.

## Actual source issue corrected

The older checked-in R12.13 manifest declares seven research files with `from: null`, but does not permit a first-time install (`allow_missing_from` absent). Consequently a compatible older Windows runtime can be blocked for absent research-only files despite a SHA-verified trusted candidate carrying them. The B07 staging builder now sets `allow_missing_from` **only** for those seven explicitly named files, **only when** the trusted old manifest still says `from: null`. The original manifest is not edited. The staged 26-file candidate manifest and per-file SHA-256 verifier remain generated from the real checked-in source and checked before installation.

Existing unknown research weights or edited local source remain blocked. Mandatory `GeoField_CAD_Analysis.py`, `fea_solver.py`, runtime `engine_runtime.py`, `fea_engine_worker.py`, `fea_previous_import.py`, essential CSS and all required missing private runtime modules remain fail-closed. No arbitrary overwrite, blind `Repair.cmd`, external download, AV bypass, or automatic paid API request.

The launcher now separates `[VERSION BLOCKER] missing_blocked`, `unrecognized_local_source`, `unsafe_link`, and `unreadable` (when present) and explicitly warns that Repair does not replace missing legacy dependencies. The user should not rerun the app just to regenerate these diagnostics: the **previous JSON file already exists** in the screenshot. To investigate unknown checksums the existing JSON may be inspected/shared after checking it for local metadata. File hashes alone **cannot prove** source compatibility; B07 real Windows verification is still required.

## Required next action

1. Obtain the **already-generated** `geofield_version_compatibility.json` from the failed 2026-10-28 launch. Review any paths/private metadata before sharing; the normal report stores relative source names and digests, not raw STEP or SQLite files.
2. Group the 26 target entries by `file_versions[*].status`. If only `unrecognized_local_source` remains, review source origin and user-authorized backed-up exact-hash migration; do not bypass incompatible APIs.
3. If `missing_blocked` contains CAD/FEA/legacy dependencies or `unsafe_link`/unreadable entries exist, require the real original installed runtime or supported recovery path. No source fabrication.
4. After a compatible install source is confirmed and code validation is green, run the **one** B07 Windows application/solver/graphics/ML/report acceptance test. Do not mark the software fully working based only on source-only CI.

This is a targeted correction plus fresh Linux/Windows **disposable** candidate verification, not evidence that the user-installed runtime is compatible.
