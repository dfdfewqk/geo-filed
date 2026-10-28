# GeoField B03 — verified FRD stress visualization

## Implemented in this PR

- Reuses the original CAD WebGL renderer, same camera, the verified FRD field, and existing MPa range control. Does **not** alter solver values, STEP files, SQLite or mesh geometry.
- Draws the hottest surface-node marker **only** after comparing A06 `surface_evidence` provenance, run/CAD/case identity, units, stress interpretation, peak MPa and peak coordinates against the returned arrays and independently verified FRD global result.
- The marker is explicitly a **2D projection** of a verified surface node. It does not establish visibility, a CAD face, causality, a global/interior peak coordinate or engineering safety.
- Clearly distinguishes **surface node peak (MPa)** and **whole-model nodal maximum (MPa)**. The latter has no proven global peak coordinate. Red is a relative visualization high end, not a material threshold or certified stress concentration cause.
- An always-visible summary shows peak magnitude and mm coordinates without zoom. The existing gradient legend shows the color-scale ceiling in MPa, including manual clipping.
- The previously verified read-only restore route now attaches A06 evidence to eligible restored fields. If a legacy field cannot be verified, the numeric restore remains available but its 3D rendering is suppressed.
- Updated frontend cache key so older browser JS is not mistakenly used.

## Checks and remaining boundaries

- `node src/tests/test_fea_b03_stress_visual.js`: runs the original browser functions in a synthetic test harness, checks valid binding, run/units/coordinates/global-vs-surface distinction and rejects tampered peak evidence without altering prior visible data.
- `node --check src/payload/frontend/cad.js`; all tracked Node regressions and the existing Python/Windows CI on PR.
- Browser WebGL visual review and actual installed Windows Gmsh/CalculiX FRD behavior are **not** proved by CI. Final end-to-end Windows review stays at B07. B04 handles displacement exaggeration/camera switching (no new camera changes are introduced by B03).
