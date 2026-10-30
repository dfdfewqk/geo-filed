# GeoField CAD · ML · FEA

Windows STEP analysis, Gmsh mesh generation, CalculiX FEA, FRD-based 3D stress/displacement visualization, and separate research ML.

## Important: GitHub source ZIP vs Windows app ZIP

**GitHub `Code → Download ZIP` is a development checkout, not an installable GeoField update.**
Its tracked `src/manifest.json` and `src/verify_package.py` are historical staging inputs,
so running `src/GeoField_Start.cmd` from a source checkout will not pass current
release-file checks. Do not edit signed SHA-256 values or disable antivirus to bypass this.

- For a **read-only check of your existing Windows runtime**, open
  `src/GeoField_Dev_Runtime_Check.cmd` from the developer checkout.
  This does **not** start or update GeoField. Optional `--check` probes backend imports.
- For **actual Windows app installation/update**, obtain the separately produced
  `GeoField-WINDOWS-REPAIRED-CANDIDATE-NOT-FINAL` build artifact from a successful
  `GeoField Windows verified-source repair audit` GitHub Actions run. Extract its
  **contents** together and verify `verify_package.py` before using its
  `GeoField_Start.cmd`. This is a **test candidate**, not a production release.
- Keep existing CAD, FEA, SQLite, STEP, private ML source and model checkpoints in place.
  A source checkout is not a replacement for your installed runtime.
  The developer bridge cannot bypass OS-level read permissions and does not
  establish actual FEA accuracy or DeepSeek paid API connectivity.

## Repository status
- **Baseline:** R12.13 integrated validation candidate + mesh-plan change guard (2026-10-21).
- **Shared source:** `src/` contains the complete update-package directory layout (including installer, Python backend, frontend, tests and ML research weights).
- **Example geometry:** `fixtures/L_bracket.step` (public generic L-bracket example).
- **Last locally reported automated suite:** 111 Python checks (as of source package). GitHub CI has **not** been run or verified.
- **Actual Windows:** single FEA run and 3D display previously observed; the latest package and three independent mesh runs remain unverified.

## How to start
1. Read [handoff](docs/HANDOFF.md) and [parallel development rules](docs/WORKSTREAMS.md).
2. From `src/`, inspect the existing `README_설치방법.txt` and `manifest.json`; run `python -m pytest tests -q` in an appropriate development environment.
3. Run `python verify_package.py` only against a complete, unchanged distribution. The ZIP update still expects the existing compatible Windows GeoField runtime and solver dependencies.
4. Do not overwrite existing installed STEP, SQLite, INP, STA, FRD or ML weights.
5. Do not claim a calculation is mesh-converged merely because CalculiX completed.

## Two parallel ChatGPT workstreams
- `work/fea-validation`: solver / mesh convergence / loads / FRD numerical accuracy.
- `work/cad-ml-integration`: CAD / ML / 3D UI / integration and deployment.
- Both branches fork from this common `main` baseline. Changes land through reviewed PRs and full regression tests.

This is a **public** repository. No personal databases, private project geometry, machine logs, secrets, or raw user histories should be committed.
