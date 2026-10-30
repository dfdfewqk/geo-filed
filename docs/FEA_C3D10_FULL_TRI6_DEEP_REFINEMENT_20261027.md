# GeoField C3D10 full Tri6 — public L-bracket 1.0 mm continuation (2026-10-27)

**Status:** research numerical sensitivity screen passed on **one locked case**; **NOT** mathematical convergence or structural design approval.

## Input identity, not the user's Windows result

- Public original CAD: `fixtures/L_bracket.step`, SHA-256 `fe65841074c5fc6bd74442b147e5688490ec1ad79d5fb1e41bdccd3514bccf32`.
- Fixed plane: verified Gmsh CAD plane centroid `(0,0,25)` mm; loaded plane centroid `(25,0,0)` mm; resolved actual face IDs from OpenCASCADE.
- Linear elastic isotropic Young modulus **68,900 MPa**, Poisson ratio **0.33**; total external force **29.41995 N**, direction **−Z**, **self-weight OFF**. Not the user's SUS304, 10 kg, +X Windows video case.
- `mesh_request.element_type=C3D10`, `mesh_request.traction_model=straight_tri6_full_consistent`. This is **straight** quadratic tetrahedral shape interpolation and full consistent Tri6 surface nodal force, with direct fixed-node `*CLOAD` subtracted from printed fixed `RF` for physically corrected support reaction audit. **Not a curved higher-order CAD-surface representation**.
- The real **production** `src/payload/fea_solver.py` creates Gmsh volume mesh, INP, runs CalculiX, independently parses STA/DAT/FRD, verifies CLOAD, computes corrected RF residual and saves real field values. No synthetic FEA or mesh extrapolation.

## Genuine 3-level continuation, separately executed

| Gmsh target mm | C3D10 nodes | Tetrahedra | Maximum nodal von Mises MPa | Maximum displacement mm |
|---:|---:|---:|---:|---:|
| 1.7 | 22,082 | 11,881 | 22.198217708 | 0.090089986 |
| 1.3 | 39,489 | 21,802 | 23.330617998 | 0.090649900 |
| 1.0 | 80,181 | 47,963 | 23.327196029 | 0.090910616 |

Adjacent changes relative to the finer result:
- 1.7→1.3 mm: max stress **4.8537%**, max displacement **0.6177%**.
- 1.3→1.0 mm: max stress **0.0147%**, max displacement **0.2868%**.
- The 5%-per-pair **review screen** passes. Actual C3D10 local stress maxima are more stable here than C3D4 for the independent published reference case, but passing does **not** imply a stress singularity has been excluded or pressure is exact on curved surfaces.
- Corrected real fixed reaction force residual for the 1.0 mm run was **~1.54×10⁻⁶ N**, a force balance cross-check only.

Actual full CI + raw INP/STA/DAT/FRD/field artifact: [Run 40435060272](https://github.com/dfdfewqk/geo-filed/actions/runs/40435060272). Previous three-mesh [2.25/1.7/1.3 full Tri6](https://github.com/dfdfewqk/geo-filed/actions/runs/40434606974).

The `GeoField C3D10 deep refinement Tri6 research` workflow performs these real calculations and opts into a **fail-closed 5% regression screen** only for the locked fixture. In general use the 5% diagnostic is advisory and model-specific; **do not silently replace C3D4 default or change previously signed case SHA**.

## Remaining limits

1. A user-created structural FE case with different geometry, material, fixed/load faces or force **requires its own** verified numerical sensitivity; the prior Windows video used C3D4 SUS304 98.0665 N (+X) and must **not** inherit this public benchmark's conclusions.
2. Curved surfaces, CAD shape representation errors, quality of volume elements, local support/load idealization, nonlinear contacts, yield criteria, and peak-stress singularities need separate engineering verification. Mathematical convergence and strength/safety are **not certified**.
3. Windows physical deployment and persisted SQLite/3D restoration on the user's PC remain independent unverified acceptance steps, not implied by Ubuntu CI.
