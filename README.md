# GeoField CAD · ML · FEA

Windows STEP/CAD analysis, Gmsh mesh generation, CalculiX finite-element analysis, FRD-based 3D stress/displacement display, and independent research ML.

## Baseline
- **Source baseline:** GeoField R12.13 integrated final candidate + mesh-plan change guard (2026-10-21).
- **Current verification:** developer-side Python tests, static checks and archived FE result comparisons; latest Windows integrated/three-mesh run **not yet confirmed**.
- **Do not treat** a completed calculation as mesh convergence or interpret a red stress color as structural failure.
- **Data protection:** do not commit personal SQLite databases, Windows runtime directories, confidential STEP files, private FEA histories, tokens, or build caches.

## Repository layout
- `src/` — original integrated package runtime source (kept in its own layout)
- `tests/` — regression and validation tests
- `docs/` — handoff, work allocation and verification status
- `fixtures/` — separately approved, non-private test geometries / numerical evidence, when available

## Two-chat collaboration
1. Use the same baseline on `main` as the authoritative version.
2. Work separately in `work/fea-validation` and `work/cad-ml-integration`.
3. Avoid concurrent edits of shared integration files; propose changes by PR and run all tests before merging.
4. No direct edits of STEP, SQLite, INP, FRD, STA or ML weights without an explicitly reviewed migration plan.
5. Log test status honestly: automated-only vs actual Windows/Gmsh/CalculiX execution.

See `docs/HANDOFF.md` for priorities and `docs/WORKSTREAMS.md` for responsibilities.
