# -*- coding: utf-8 -*-
"""Read-only GeoField installed-runtime dependency audit.

Existing private runtime files MUST NOT be fabricated, copied from unrelated
machines, or silently replaced by the 17-file update payload. A "present"
finding confirms a regular nonempty local file only; it is NOT evidence that
the module imports, CAD meshes, or CalculiX succeeds.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys

# Existing modules required by top-level imports of GeoField_CAD_Analysis.py,
# by fea_solver.py, and by the original 3-mesh engine. Never put these on the
# installer allowlist without obtaining actual verified release bytes first.
EXISTING_REQUIRED = (
    "analysis_hub.py",
    "cad_common.py",
    "decision_engine.py",
    "engine_runtime.py",
    "fea_compare.py",
    "fea_engine_worker.py",
    "fea_event_store.py",
    "fea_geometry_crosscheck.py",
    "fea_improvement_review.py",
    "fea_mesh_quality.py",
    "fea_previous_import.py",
    "fea_restore.py",
    "fea_stress_hotspots.py",
    "fea_stress_mesh_link.py",
    "fea_unified_report.py",
    "geometry_dimensions.py",
    "gravity_evidence.py",
    "history_store.py",
    "integrated_results.py",
    "legacy/geofield_v823_extension.py",
    "ml/brepmfr_worker.py",
    "r17_previous_catalog.py",
)

# The solver and A's physical comparison files are updated by the package, but
# must exist before upgrade if a historic import uses them before installation.
UPDATABLE_REQUIRED_BEFORE_INSTALL = (
    "GeoField_CAD_Analysis.py",
    "fea_convergence.py",
    "fea_mesh_series.py",
    "fea_solver.py",
)


def _presence(path, runtime):
    """Determine file health without opening or executing the module."""
    if path.is_symlink() or any(
        parent.is_symlink() for parent in path.parents if parent != runtime.parent
    ):
        return "unsafe_symlink"
    if not path.is_file():
        return "missing"
    try:
        if path.stat().st_size == 0:
            return "empty"
    except OSError:
        return "unreadable"
    return "present_unverified"


def _tool_hint(name, env=None):
    env = os.environ if env is None else env
    alternatives = {
        "freecad": ("GEOFIELD_FREECAD_EXE", "FreeCAD.exe", "FreeCAD"),
        "calculix": ("CALCULIX_EXE", "ccx.exe", "ccx"),
        "gmsh_python": ("GEOFIELD_GMSH_PYTHON",),
    }
    for token in alternatives[name]:
        value = env.get(token) if token.isupper() else shutil.which(token)
        if value and Path(value).is_file():
            return {"detected": True, "source": token,
                    "note": "File location detected only; no solver was executed"}
    return {"detected": False, "source": None,
            "note": "Not located by this passive hint scan; may exist elsewhere"}


def audit_runtime(root):
    """Report whether files expected on the *existing* installed runtime exist.

    Only read-only pathlib inspections and passive path hints. No network,
    subprocess, file writes, dependency installs, CAD or FEA calculations.
    """
    runtime = Path(root)
    if runtime.is_symlink() or not runtime.is_dir():
        return {
            "ready_for_update": False,
            "runtime_found": False,
            "required_count": len(EXISTING_REQUIRED) + len(UPDATABLE_REQUIRED_BEFORE_INSTALL),
            "missing": ["runtime_root"],
            "unsafe": [],
            "empty_or_unreadable": [],
            "existing_runtime_dependencies": list(EXISTING_REQUIRED),
            "updatable_old_runtime_dependencies": list(UPDATABLE_REQUIRED_BEFORE_INSTALL),
            "module_states": {},
            "python_executable": sys.executable,
            "engine_hints": {},
            "note": "No installation or runtime execution performed",
        }
    required = EXISTING_REQUIRED + UPDATABLE_REQUIRED_BEFORE_INSTALL
    states = {name: _presence(runtime.joinpath(*name.split("/")), runtime)
              for name in required}
    missing = sorted(name for name, state in states.items() if state == "missing")
    unsafe = sorted(name for name, state in states.items() if state == "unsafe_symlink")
    invalid = sorted(name for name, state in states.items()
                     if state in ("empty", "unreadable"))
    return {
        "ready_for_update": not (missing or unsafe or invalid),
        "runtime_found": True,
        "required_count": len(required),
        "missing": missing,
        "unsafe": unsafe,
        "empty_or_unreadable": invalid,
        "existing_runtime_dependencies": list(EXISTING_REQUIRED),
        "updatable_old_runtime_dependencies": list(UPDATABLE_REQUIRED_BEFORE_INSTALL),
        "module_states": states,
        "python_executable": sys.executable,
        "engine_hints": {
            "freecad": _tool_hint("freecad"),
            "calculix": _tool_hint("calculix"),
            "gmsh_python": _tool_hint("gmsh_python"),
        },
        "python_modules_detected_unverified": {
            name: importlib.util.find_spec(name) is not None
            for name in ("cadquery", "OCP", "gmsh")
        },
        "note": ("Required file presence only. Does not verify Python imports, STEP "
                 "geometry, Gmsh, CalculiX, FEA accuracy or WebGL."),
    }


def status_summary(report):
    if report.get("ready_for_update"):
        return "Installed runtime dependency file checks passed (import/solver NOT verified)"
    return "; ".join(
        str(kind) + "=" + ",".join(report.get(field) or [])
        for kind, field in (("missing", "missing"), ("symlink", "unsafe"),
                            ("invalid", "empty_or_unreadable"))
        if report.get(field)
    ) or "Existing runtime is unavailable"


if __name__ == "__main__":
    import json
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_path", type=Path)
    args = parser.parse_args()
    result = audit_runtime(args.runtime_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ready_for_update"] else 24)
