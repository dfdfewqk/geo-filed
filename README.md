# GeoField CAD · ML · FEA

Windows STEP analysis, Gmsh mesh generation, CalculiX FEA, FRD-based 3D stress/displacement visualization, and separate research ML.

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
