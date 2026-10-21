# GeoField development handoff (2026-10-21)

## Objective
Complete the existing Windows STEP → CAD B-Rep → FEA conditions → Gmsh → CalculiX → FRD → 3D and history flow. Preserve existing working behavior. Do not add decorative features or invent solver / ML results.

## Source of truth
- Baseline locally generated archive: `GeoField_R12_13_최종통합_메시계획_변경차단.zip`, SHA-256 `1a492b832b830168e26c716fb2a78f9baaa8e904ac03aaaa07a6f6b133376fbf`.
- Unpacked source is version-controlled under `src/` with its original directory structure and `src/manifest.json`.
- Generic L-bracket STEP SHA-256: `fe65841074c5fc6bd74442b147e5688490ec1ad79d5fb1e41bdccd3514bccf32`.
- R12 research ML model joblib SHA-256: `df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0`.

## Previously observed facts vs unverified
- Archived **3 kg** FEA: 2,798 nodes, 8,611 C3D4 elements; 609 applied load nodes; 29.41995 N resultant; center approximately (25.3897, 0.0048, 0) mm. FRD max von Mises ~9.183541 MPa; max displacement ~0.0131454 mm. The underlying private archive is **not included** here.
- Earlier Windows screen recording showed a **10 kg** run and 3D visualization, but the current Git baseline has **not** independently reproduced its INP/FRD.
- Reported developer-side Python tests: **111 passed** for latest baseline; this is not a GitHub Actions run.
- Three independent meshes (coarse/medium/fine) have **not** yet been freshly solved and compared on Windows. Mesh convergence is not demonstrated.
- Latest auto port-8600 recovery and newest package update are not yet verified in the user’s Windows environment.

## Highest priority remaining
1. On actual Windows with Gmsh and CalculiX, run 3 mesh sizes using the *same* CAD SHA, material, load and boundary conditions. Independently verify saved INP/STA/FRD and obtain stress/displacement variation and maximum-stress location movement; clearly distinguish completion vs convergence.
2. Recheck applied resultant and moments. In archived 3 kg test, excluding 18 shared fixed/load nodes shifted load center ~0.39 mm. Do not mistake force conservation for moment conservation.
3. Ensure reported maxima, 3D field, saved report, and history refer to the same verified run and SHA; prevent stale CAD/results mixing.
4. Regress STEP replacement, CAD/BRep, independent research ML, record restore, WebGL colors and Windows single-launcher update/rollback.
5. Only after these: one final Windows end-to-end acceptance session.

## Rules
Preserve STEP, SQLite, INP, FRD, STA and ML weights. Treat archived numerical evidence separately from simulations/mocks. Keep baseline on `main`; use PRs from work branches.
