GeoField local runtime source review helper (NOT AN INSTALLER)
===================================================================
Purpose: identify the legacy Python engine modules currently absent from the
GitHub source tree, without touching the installed runtime.

In Windows File Explorer, extract this helper artifact once, then run
GeoField_Runtime_Source_Review.cmd with ordinary user permissions.

The helper:
- reads only the fixed list of Python modules from the installed legacy
  GeoField runtime (no scripts inside that runtime are executed);
- rejects symbolic links, empty/oversized files and unknown filenames;
- writes a NEW review ZIP under your Downloads folder;
- adds a manifest with per-file SHA-256 and missing-module status;
- never copies STEP, SQLite, INP/STA/FRD, weights or unrelated files;
- does not upload or install anything.

IMPORTANT: Python sources could contain local secrets, paths, or non-public
code. Inspect the review ZIP and manifest before sharing it with anyone.
Do not upload the ZIP directly into a public GitHub repository. A SHA-256
fingerprint does not mean the local source is safe or compatible. Missing
modules mean the existing GeoField code still cannot run on a fresh PC.
