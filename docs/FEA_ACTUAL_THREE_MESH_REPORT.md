# GeoField FEA — genuine solver three-mesh studies (2026-10-22)

## Scope and evidence

- **Computational method:** original `src/payload/fea_solver.py::run_real_fea()` with actual Gmsh Python API **4.12.1** and CalculiX ccx **2.21** installed on the GitHub Actions Ubuntu runner.
- **Geometry:** approved public `fixtures/L_bracket.step` with SHA-256 `fe65841074c5fc6bd74442b147e5688490ec1ad79d5fb1e41bdccd3514bccf32`.
- **Material:** isotropic, E=68,900 MPa, ν=0.33; **load:** 29.41995 N in −Z, on Z=0 face, support on X=0 face; **gravity:** off.
- Each solve has a separate signed case, a distinct Gmsh tetra mesh, actual `ccx` subprocess, and native `geofield_case.{inp,sta,frd,dat}` evidence. Each result was parsed by production code, and fixed-node reactions were checked for force and moment equilibrium. No solver or FRD value was mocked.
- Workflow results: [first 3 runs](https://github.com/dfdfewqk/geo-filed/actions/runs/39703111645) and [independent finer 3 runs](https://github.com/dfdfewqk/geo-filed/actions/runs/39703468073). The complete raw artifacts are uploaded to the individual GitHub Actions runs with 7-day retention; download separately for long-term archiving if needed.

## Actual mesh and solution measurements

| Target element size (mm) | Nodes | C3D4 tets | Mean longest tet edge (mm) | Max nodal von Mises (MPa) | Max displacement (mm) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4.20 | 818 | 2,284 | 4.12464 | 4.733333 | 0.026414 |
| 3.00 | 1,166 | 3,269 | 3.85952 | 4.842480 | 0.026059 |
| 2.25 | 1,801 | 5,048 | 3.43120 | 5.011163 | 0.028770 |
| 1.70 | 3,575 | 11,881 | 2.48334 | 9.728833 | 0.047432 |
| 1.30 | 6,281 | 21,802 | 2.00058 | 10.794677 | 0.055517 |

The **2.25 mm** run was independently repeated in the second study, and the INP SHA-256, node/tet counts, maximum stress and displacement were exactly the same. The FRD files' raw SHA-256 differ across repetitions, so only identical computed results and INP (not byte-identical FRD) are claimed.

## Adjacent changes and stability verdict

| Pair (mm) | Max stress relative change | Max displacement relative change |
| --- | ---: | ---: |
| 4.20 → 3.00 | 2.254% | 1.362% |
| 3.00 → 2.25 | 3.366% | **9.423%** |
| 2.25 → 1.70 | **48.492%** | **39.344%** |
| 1.70 → 1.30 | **9.874%** | **14.563%** |

- **All six physical solver runs completed, and all six fixed-node reaction equilibrium checks passed.** Applied load magnitude and moment are independently comparable. Within each of the two studies, true mean tetra longest edges decreased monotonically while element and node counts increased.
- **The existing five-percent numerical-stability review criterion FAILED in both studies.** Max nodal stress and displacement are NOT mesh-independent in these tests. No mathematical convergence, structural safety certification or material strength acceptance may be inferred.
- Nodal von Mises values are extrapolated from first-order C3D4 elements. The most severe values may be sensitive to local singularities at constraints/load edges. Additional mesh convergence investigation and a physically appropriate stress/deflection quantity of interest are required before trusting a final design limit. Increasing mesh count alone is not a proof of convergence.
- **Linux CI success does not validate Windows deployment, client 3D view, ZIP installer, updated manifest or full persisted-history restoration.** Those belong to Chat B's final integration acceptance process.

## Further acceptance conditions

1. Determine physical/numerical cause of the continued stress/deflection changes before accepting a design result (e.g. local boundary application, corner singularities, linear-tetra mesh sensitivity, surface approximation).
2. Verify the same CAD/material/load/support identity for subsequent studies and do not relax the five-percent diagnostic merely to obtain a green badge.
3. For final Windows acceptance, install the merged verified A+B version, run CalculiX with `.dat` reaction extraction, compare real `.inp/.sta/.frd` values against 3D/SQLite history, then run the three-mesh workflow with the actual CAD model.
4. Preserve the archived actual solver evidence; never overwrite user's private STEP, SQLite, FE runs or ML weights.

**Status:** Real 3-mesh execution and comparative diagnostic performed; **numerical convergence not demonstrated**. Production deployment and full Windows end-to-end acceptance remain pending. This report does not assert that GeoField development is complete.