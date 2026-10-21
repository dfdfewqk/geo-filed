# Two-chat work allocation and merge policy

## Chat A — `work/fea-validation`
Owner of `src/fea_solver.py`? In the original package the solver is `src/payload/fea_solver.py`. Focus on real Gmsh/CalculiX three-mesh runs, INP load sums/moments, FRD nodal stress/displacement and numerical convergence. Write numerical tests and evidence; do not change the UI without coordination.

## Chat B — `work/cad-ml-integration`
Own CAD B-Rep handling, R12 research ML (kept separate from FEA), 3D display, job persistence and safe installation. Validate public endpoints, STEP/result binding, frontend colors, port recovery, Windows install, and integration.

## Shared files / conflict rules
The backend `src/payload/GeoField_CAD_Analysis.py` couples both workstreams. Before changing it, coordinate via an issue or PR; avoid independently overwriting the same functions.
Both chats must:
- Start from latest `main`, commit to **their own branch**, and submit focused PRs rather than pushing directly to `main`.
- Record files touched, test command/output, mock-vs-real status, and any unverified Windows behavior.
- Never modify existing STEP/SQLite/INP/STA/FRD/ML weights in place.
- Preserve the SHA-256 integrity and original numerical results; update manifests only for actual code changes.
- Merge one PR at a time; rebase/update the other branch, then rerun all relevant tests.

## Next-day pickup
1. Open `docs/HANDOFF.md`.
2. Fetch `main`, verify changed files, and check outstanding PRs/issues.
3. Continue only the assigned branch's unfinished items.
4. Return a PR link and test evidence. Avoid duplicate parallel implementations.
