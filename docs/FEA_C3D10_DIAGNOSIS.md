# GeoField — C3D4 overly stiff bending response Actual C3D10 diagnostic

Date: 2026-10-22. This report records **actual CalculiX 2.21 results** for the public L-bracket STEP, not an approved engineering-design result or a production solver replacement.

## Background

The original C3D4 mesh was very sensitive to mesh refinement on a 3mm-thick bending flange. We verified 24 out of 24 SHA-256 hashes of archived INP/STA/FRD/DAT outputs for the six actual previous solve runs across two CI experiments. Re-used 2.25mm inputs/outputs agree. On the flange interior ROI 15<x<45, -10<y<10, 0.05<z<2.95mm, the count of nodes within the flange thickness changed sharply: 3.0mm target: 7 nodes; 2.25mm: 11; 1.7mm: 149; 1.3mm: 290. This indicates insufficient through-thickness resolution for the coarse first-order tetra meshes.

## Actual C3D4 vs C3D10 study

Source: https://github.com/dfdfewqk/geo-filed/actions/runs/39705351993

We generated linear tetra meshes from the unchanged public STEP, kept identical tetra corners and their CLOADs, then created shared midside nodes and real C3D10 elements. Gmsh and CalculiX ran on the Ubuntu CI host. All three quadratic STA/FRD/DAT files were produced and parsed; RF force and moment equilibrium tests passed. Both finite element types received identical loads on the **original vertex nodes**. This isolates element approximation order, but does not reproduce consistent quadratic surface pressure.

| Gmsh target size | Tet count | C3D4 displacement (mm) | C3D10 displacement (mm) | C3D4 nodal Mises (MPa) | C3D10 nodal Mises (MPa) |
|---:|---:|---:|---:|---:|---:|
| 3.0mm | 3,269 | 0.02605893 | 0.08715548 | 4.84248 | 20.63765 |
| 2.25mm | 5,048 | 0.02876992 | 0.08829596 | 5.01116 | 21.20541 |
| 1.7mm | 11,881 | 0.04743158 | 0.08948997 | 9.72883 | 22.07826 |

Adjacent quadratic changes relative to the finer solution: maximum displacement ~1.29%, ~1.33%; maximum extrapolated nodal Mises ~2.68%, ~3.95%. C3D4 results are much more mesh-sensitive. This is strong evidence that **linear tetrahedral bending stiffness is the main observed problem for this case**, in agreement with the CalculiX manual's recommendation of C3D10 for general structural calculations (https://www.dhondt.de/ccx_2.15.pdf). It does not prove that all local stresses converge or that the bracket is safe.

## Limitations and what is not done

- No production solver code was replaced. All new quadratic code is confined to a reproducible isolated research runner.
- We kept C3D4 corner CLOAD distributions instead of using the consistent 6-node quadratic face load. Uniform face pressure and true stress distribution are therefore **not validated**.
- Added midside nodes lie on the original straight linear edges; curved CAD surface representation is not newly resolved.
- The reported stress is FRD-extrapolated maximum nodal Mises, which is sensitive to location and singularities. A 5% numerical screen is not mathematical convergence or safety certification.
- Windows runtime, UI, history and case migration remain untested with true quadratic elements.

## Actual next production fix (needs dedicated implementation and cross-chat integration)

1. Add optional/validated C3D10 Gmsh tetra topology, consistent node ordering and stricter element validation to the production FEA solver.
2. Generate **consistent quadratic surface tractions**, preserving force/moment and treating fixed/load shared nodes correctly, including support reaction interpretation.
3. Upgrade the FRD nodal-field and 3D surface plotting contracts for midside nodes; do not silently drop stress peaks.
4. Keep old C3D4 run identities, INP/STA/FRD and saved SQLite histories unchanged; distinguish element type and load semantics in analysis/run IDs.
5. Run real three-mesh quadratic validation with the final proper load model, verify STA/FRD/DAT and balance, then Windows integration. Until then: current production C3D4 fine-mesh study remains numerically **not converged**.