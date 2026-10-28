# GeoField B06 — Windows source-only update candidate (2026-10-28)

## Outcome and strict boundary

The old checked-in `src/manifest.json` and `src/verify_package.py` describe an **obsolete R12.13 release**. Do **not** copy those two files (or run `src/GeoField_Start.cmd` directly from this source checkout) and call that B06. Instead the existing `src/build_integration_candidate.py` creates a separate **26-file candidate** with a SHA-256 manifest, source lock, and a newly generated exact-file `verify_package.py` in an otherwise empty staging folder. The old checked-in manifest is only a *read-only prior-version baseline*.

The 26 reviewed deployment targets include the previous 17 and nine A/B helpers:
- `fea_b02_workspace.py` — solver directory and STEP safeguards
- `fea_history_a03.py`, `fea_history_delete_a04.py` — verified history and deletion
- `fea_field_a06.py`, `fea_report_a08.py` — actual FRD field and immutable HTML reports
- `fea_compare.py`, `fea_ab_verified_comparison.py`, `fea_moment_balancing.py`, `fea_pressure_equivalence.py` — verified comparisons and FEA utility code

Source path mapping is explicit: new A/B helpers are copied from the Git-tracked `src/` or `src/payload/` path into `candidate/payload/`; the SHA-256 and byte count are calculated **after copying**. Installation never downloads missing components or accepts an arbitrary source file.

## What it does *not* provide

**Not a standalone EXE or a fresh-PC installer.** The existing Windows GeoField runtime remains necessary. At least the checked local `engine_runtime.py`, `fea_engine_worker.py`, `fea_previous_import.py`, `integrated_results.py`, `history_store.py`, FreeCAD/CadQuery, Gmsh and CalculiX components are not invented by GitHub. A B01 preflight verifies required filenames, structure, SHA-256/source API as available; successful package tests do not imply the user's Windows modules exist, import successfully, or work on real FEA. B07 will perform that verification only once on the actual Windows installation. DeepSeek calls require user consent and working credentials and are never triggered by B06.

## Safe update, recovery and rollback

1. Use the `GeoField B06 safe Windows source candidate` GitHub Actions workflow on PR #41. Both Linux and Windows test the identical trusted manifest with temporary simulated runtime directories and verify install, second-run no-op, original backup, interrupted-install recovery, and rollback paths.
2. The workflow uploads **one-extract staged files** under `GeoField-B06-SOURCE-CANDIDATE-NOT-FINAL`. Do not run a CMD from a ZIP preview. The artifact is for B07 review, **not a release recommendation**.
3. The launcher checks the generated exact-file verifier before any installation. It then checks installed source/API compatibility and Python/interpreter candidates before attempting to release port 8600. Unknown port owners, missing installed modules, blocked file types, unknown hashes or symlinks stop the upgrade.
4. Existing edited code cannot be silently overwritten: only approved prior hashes are accepted automatically; an unknown current local `.py/.js/.html` requires an **exact installed-hash-bound**, on-screen `MIGRATE CODE` approval after a complete code backup. Unknown ML weights or unrelated user files can never be approved as an automatic source migration.
5. Installer journal records intended changes, files are staged exclusively and hash-checked, then atomically replaced; a failed updated-backend check rolls back code only after comparing current installed SHA-256 and backup SHA-256. Recovery of an incomplete install refuses any unrecognized edits and preserves originals.

**Original user engineering files must not be included in package manifests or backups:** STEP, SQLite, INP, STA, FRD, unrelated ML weights and personal projects. Tests use synthetic temporary files only. If original code is missing or unknown and cannot be reviewed, stop instead of inventing a replacement.

## B07 (not executed yet)

After the source-only candidate is proven and the Windows B01 runtime inventory is reviewed, the single user-PC test should check: existing runtime detection → approved update → STEP/CAD import → actual ML availability/results → Gmsh and CalculiX workdir/INP/STA/FRD → B03 stress and B04 displacement in WebGL → B05 reports and history/compare/deletion controls (without deleting important records) → optional, explicitly consented DeepSeek request → safe restart/rollback checks. Use the existing acceptance CMD only as a **read-only check after** GeoField Start; it does not launch a server.

CI evidence is intentionally limited to code/source and temporary runtime test harnesses. It does not certify user's Windows hardware, installed binary, actual model inference, real solver execution, Defender compatibility, structural safety or free paid-provider connectivity.
