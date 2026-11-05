# GeoField — Original L-Bracket final code-side audit (2026-11-05)

## Canonical development chain

- Repository: `dfdfewqk/geo-filed`.
- Baseline: draft PR #108, head `c56315e48281cc1b28692466a7664a0761dc02d9`.
- Baseline seven-job CI: GitHub Actions run `41967062755`, all seven jobs passed. That includes a *separate* actual synthetic/fixture solver evaluation, **not** the user's original Windows STEP acceptance.
- This follow-up: draft PR #109, `work/geofield-final-mesh-delta-proof-20261105`, stacked on PR #108. Main remains unchanged.

## Code-side engineering evidence fixes

1. On every trusted three-mesh readback, cross-check each reported stress and displacement relative change against the three independently reverified solver maxima. Use the real `fea_convergence._percent_delta` convention: `abs(finer-coarser) / abs(finer) * 100`; reject zero denominators, nonfinite results and contradictions. Never show a possibly false 5% numeric stability result.
2. If an optional three-mesh readback is unverifiable, preserve the separately verified base FEA HTML report and explicitly describe the missing study. Never promote optional study ID alone to verified scientific evidence. Original STEP/INP/STA/FRD/SQLite and user model files remain untouched.
3. Correct the outdated synthetic mesh report fixture to match actual relative-change formulas instead of loosening production source checks. Add negative fixture coverage for contradictory percentages and optional invalid-study fallback.
4. Do not re-execute any solver, call external paid AI, mutate SQLite, or generate/release ZIP/EXE in these changes.

## Current automated evidence

- Workflow: `.github/workflows/geofield-final-mesh-delta-readback-ci.yml`.
- GitHub Actions run: **41969606688**, at committed code HEAD `01d5e880c3f5ae52d37caf583601e376f62319f1`: **all three jobs passed**.
  - Windows JS syntax and targeted FEA/mesh/report/history UI regressions.
  - Ubuntu JS syntax and targeted FEA/mesh/report/history UI regressions.
  - Ubuntu *all 51 committed frontend JS regression scripts*, agent Python regression suite, and real isolated SQLite archive/restart/FEA source-binding regression tests.
- There were intermediate CI failures during incremental commits: one older synthetic test used incorrect fabricated percentages; CI checkout lacked full Git history for a provenance test; standalone Python SQLite tests lacked the src import root. All were fixed in the **test fixtures or CI environment** without weakening production source checks. The final run above passed.
- Do not conflate these CI checks with the user's physical Windows, real model accuracy or a certified stress convergence claim.

## Still not verified / required final sequence

1. One *authorized* end-to-end Windows session for the user's unchanged original `L_bracket.step`: independently backup existing STEP, SQLite, models and prior results, then use a separate candidate runtime without overwriting the installation.
2. Confirm CAD SHA, signed fixed/load/material conditions, one-click base CalculiX, three actual mesh jobs, independent INP/STA/FRD values, 3D view, research ML/R12 status, rules-only AI and verified HTML export. External paid AI remains opt-in only.
3. Select one past same-STEP verified archive, compare current/old SQLite snapshots read-only and confirm restart retention. Capture execution IDs, log outcomes, hashes, screen/report observations and backup intact status once, following `docs/GeoField_ONE_PASS_WINDOWS_ACCEPTANCE_20261105.md`.
4. Keep the draft branches unmerged and do not call the program complete/ship an EXE or ZIP before actual acceptance.

## Engineering truth boundaries

No independent held-out labeled ML accuracy, yield-allowable safety factor, proven hole/fillet causal stress attribution or certified numerical convergence has been established. Current FRD spatial peaks and three-mesh numerical stability are valuable observations only. The report's toggle OFF prevents *external paid* AI text/requests but still includes the *local rules-only* evidence-based explanation; this distinction must remain explicit.
