# GeoField Windows updater — full code audit after user's 2026-10-28 error

## Observed, not guessed

User's first downloaded 26-file B06 candidate passed the package integrity check but failed **read-only installed-version compatibility** (exit 25). The second screenshot after PR #42 explicitly shows every listed blocker as `unrecognized_local_source`: 15 paths, covering core CAD/FEA, frontend UI, ML bridge/research Python modules **and** `ml/r12_research/report.json`. Thus the screenshot is *not* evidence of missing modules, invalid download, CalculiX failure, or missing ML model weights.

The root issue was systemic: `runtime_compatibility.assess_compatibility` declared all fifteen SHA-256 differences a single non-approvable group because it allowed an explicit backed-up migration only for `.py/.js/.html`, never the known R12 reference `report.json`. The launcher never reached the **one-time user consent**, even though it could safely identify all exact installed hashes. The prior PR #42 first-install allowance for absent R12 files did not resolve *present but different* files.

## Full audit and fixes

| Area | Audit result and correction | Safety boundary |
| --- | --- | --- |
| Package source | Staged candidate is still exactly 26 known paths, SHA-256 manifest and source lock. Old `src/manifest.json` remains a historic baseline, never the new published candidate | No untracked files, raw Windows module invention or arbitrary overwrite |
| Version inventory | Classifies every `unrecognized_local_source`, `missing_blocked`, `missing_allowed`, `unsafe_link`, `unreadable`, and bounded reference report | Old installed files are only hashed; no code executed and no private CAD/SQLite read |
| Multi-file installed-version mismatch | An unknown-but-present `.py/.js/.html` and **only** the packaged `ml/r12_research/report.json` can be reviewed as one exact-hash approval set | No generic `.json`, `.joblib`, ML weights, STEP, FRD, SQLite or foreign files accepted |
| Explicit approval | Before any server stop or installation, show exact code file names and the separate reference-report name; ask for `MIGRATE CODE` **once**, with backups and potential rollback stated | User can decline without changing code; exact SHA mismatches at apply-time abort |
| Upgrade staging | Original bytes are backed up and checksummed. Bounded reference report (max 4,000,000 bytes) is treated as package-supplied research metadata rather than model weights | Code-only approved sources and bounded report; stage/rollback retains per-file journals |
| Startup recovery | Updated backend gets checked before running; failed initial health check rolls back only the changes from that invocation; existing STEP/SQLite/INP/STA/FRD stay untouched | Real Gmsh/CCX, paid API and GPU still require B07 actual PC acceptance |
| Launcher UX | Build label updated to distinguish fixed version, and Repair instruction still refuses missing/unsafe/unknown model runtime prerequisites | No antivirus bypass, global process killing, dependency download or auto paid API |
| CI regression | Added a regression that reproduces **all fifteen paths** from the screenshot, rejects no-consent install, checks every original SHA backup, and restores all fifteen on rollback. Other cases cover invalid model approval, malicious/oversized report, changed approved SHA, unknown symlinks and mandatory modules | Linux/Windows *disposable* runtime only |
| Other stale tests | Reconciled legacy `test_agent_release_candidate` and Windows artifact messages still expecting 17 vs current 26 payloads | Future CI failures become visible rather than ignored |

## Exact status

This source correction does **not** prove that any of the user's present unknown local code actually implements the same API. The launcher's independent installed-runtime symbol/dependency audit must pass, otherwise exit 26/27 remains correct. The candidate cannot install absent private `engine_runtime.py`, `fea_engine_worker.py`, `fea_previous_import.py`, or any unreviewed Windows runtime. A successful read-only audit does not certify FEA physical accuracy. The user has a previously created `geofield_version_compatibility.json` which would provide hashes and installed runtime API statuses; the screenshot alone cannot prove all those statuses.

**Do not ask for repeated actual FEA tests.** First run preflight once on the real Windows installation after source integration, keep all original data and backups, and reserve real STEP/CAD/ML/Gmsh/CCX/FRD/WebGL/AI/report end-to-end for the B07 final acceptance only.
