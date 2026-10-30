# GeoField B04 — verified 3D displacement / camera (2026-10-28)

## Scope

- Reuses B03's existing WebGL and Canvas2D FRD surface renderer. No new menu, solver math, CAD source, database, or user files are modified.
- Before installing a live FEA field, verifies the A06 `surface_evidence` displacement units (mm), run/CAD/case identities, original surface peak position, nodal displacement norm, surface maximum and independently verified full FRD maximum. Invalid evidence is rejected before changing the displayed field.
- Displays **verified surface maximum displacement and its mm coordinate** separately from the **whole-model maximum displacement**. The latter's position is explicitly unverified: it might be interior; a surface coordinate is never silently substituted.
- Node color is based on the unscaled norm of original FRD `displacements_mm`, so the legend stays actual millimetres even if the model is rendered at ×5 or ×20.
- The existing checkbox and select affect **only display geometry**. Off = undeformed model; ×1 = physical displacement geometry; ×5 / ×20 = exaggerated rendering. Unexpected dropdown values fail closed to no deformation.
- Stress ↔ displacement ↔ no-contour, the deformation checkbox, and the scale selection do **not** reset the user's main camera quaternion, pan, zoom or section clipping. View/reset commands remain explicitly user-controlled. The archived read-only viewer preserves its own yaw/pitch/zoom when changing visualization modes.
- In archived FEA preview, displacement peak evidence is rechecked against the same verified run. Preview labels distinguish unscaled mm colors and screen geometry factor; legacy/hotspot contexts lacking preview-specific evidence do not invent a peak coordinate.

## Automated evidence / limits

- `src/tests/test_fea_b04_displacement_camera.js`: original browser functions, synthetic fixtures, invalid evidence (missing/incorrect mm, run, case, peak, global), mode changes and camera preservation.
- Existing B03 stress visualization and FEA history tests updated only to include A06 displacement evidence in synthetic fixtures.
- GitHub full PR Actions gate includes original JS, Python and disposable Windows tests. **No user Windows Gmsh/CalculiX or real WebGL device evidence** is claimed; B07 remains the only user-machine end-to-end check.
