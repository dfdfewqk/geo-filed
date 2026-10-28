# -*- coding: utf-8 -*-
"""Read-only GeoField installed-runtime dependency audit.

Existing private runtime files MUST NOT be fabricated, copied from unrelated
machines, or silently replaced by the 17-file update payload. A "present"
finding confirms a regular nonempty local file only; it is NOT evidence that
the module imports, CAD meshes, or CalculiX succeeds.
"""
from __future__ import annotations

import ast
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

# A11 adds these NEW GitHub backend helpers. They do not exist in legacy
# Windows runtimes, so they must NEVER enter EXISTING_REQUIRED or the existing
# installation pre-update presence audit. Antigravity B06 must explicitly map
# them into the installed runtime directory after B01 source verification.
# Until that happens, "GitHub source available" does NOT mean runnable binary.
A11_NEW_BACKEND_MODULES = (
    "fea_history_a03.py",
    "fea_history_delete_a04.py",
    "fea_field_a06.py",
    "fea_report_a08.py",
)

# The solver and A's physical comparison files are updated by the package, but
# must exist before upgrade if a historic import uses them before installation.
# Static frontend asset is required for serving GET /cad.css, but is NOT
# a Python module and must never be included in the source recovery ZIP.
FRONTEND_REQUIRED = ("frontend/cad.css",)

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
            "required_count": len(EXISTING_REQUIRED) + len(UPDATABLE_REQUIRED_BEFORE_INSTALL) + len(FRONTEND_REQUIRED),
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
    required = EXISTING_REQUIRED + UPDATABLE_REQUIRED_BEFORE_INSTALL + FRONTEND_REQUIRED
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



# Public GeoField_CAD_Analysis and fea_solver both depend on this *legacy*
# runtime module. Older R12 installed sources may have the correct filename
# while lacking required functions. Detect that BEFORE closing a running app.
ENGINE_RUNTIME_EXPORTS = (
    "engine_python",
    "prepare_python_environment",
    "gmsh_python_status",
    "REQUIRED_ML",
    "REQUIRED_GMSH",
)


def audit_engine_runtime_contract(root):
    """Statically inspect only a known engine_runtime.py, never execute it.

    This checks Python-level API names, not function signatures or actual
    imports/DLLs/solver availability. An incompatible old API is a hard block
    for upgrading the running GeoField instance. No user files are changed.
    """
    base = Path(root)
    source = base / "engine_runtime.py"
    result = {
        "schema": "geofield-engine-runtime-api-v1",
        "status": "blocked",
        "compatible": False,
        "module": "engine_runtime.py",
        "required_exports": list(ENGINE_RUNTIME_EXPORTS),
        "missing_exports": list(ENGINE_RUNTIME_EXPORTS),
        "read_only": True,
        "installed_code_executed": False,
        "verified_imports_or_solver": False,
    }
    if base.is_symlink() or not base.is_dir() or source.is_symlink():
        result["reason"] = "missing_or_unsafe_runtime"
        return result
    try:
        if not source.is_file() or not 0 < source.stat().st_size <= 256 * 1024:
            result["reason"] = "missing_empty_or_oversized_module"
            return result
        tree = ast.parse(source.read_text(encoding="utf-8"), filename="engine_runtime.py")
    except (OSError, UnicodeError, SyntaxError, ValueError):
        result["reason"] = "unreadable_or_invalid_python"
        return result
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.add(alias.asname or alias.name.split(".")[0])
    missing = sorted(set(ENGINE_RUNTIME_EXPORTS) - names)
    result["missing_exports"] = missing
    result["compatible"] = not missing
    result["reason"] = "required_top_level_names_present" if not missing else "required_api_names_absent"
    result["status"] = "static_api_present_not_executed" if not missing else "blocked"
    return result


def _declared_top_level_names(tree):
    """Conservatively detect names made available by normal top-level imports."""
    names=set()
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target,ast.Name):names.add(target.id)
        elif isinstance(node,(ast.Import,ast.ImportFrom)):
            for alias in node.names:
                if alias.name!='*':
                    names.add(alias.asname or alias.name.split('.')[0])
    return names


def audit_backend_import_contract(runtime_root, candidate_payload):
    """Read-only audit of ALL direct installed-module API imports by new FEA.

    Verify that existing local modules actually define the names used by the
    NEW staged backend and solver. NEVER import or execute installed files and
    NEVER copy original 2026-10-15 modules into a later user's installation.
    A pass is a static contract only; imports, DLLs, CAD, ML and CCX remain
    runtime acceptance checks. Paths and local source contents are not logged.
    """
    root=Path(runtime_root)
    payload=Path(candidate_payload)
    result={'schema':'geofield-installed-source-api-v1','compatible':False,
            'read_only':True,'installed_code_executed':False,
            'candidate_code_executed':False,'solver_executed':False,
            'verified_imports_or_solver':False,'required_modules':{},
            'missing_or_invalid_modules':[],'missing_exports':{},
            'reason':'not_checked'}
    if (not root.is_dir() or root.is_symlink() or not payload.is_dir() or
        payload.is_symlink()):
        result['reason']='installed_runtime_or_candidate_missing'
        return result
    existing=set(EXISTING_REQUIRED)
    required={}
    for name in ('GeoField_CAD_Analysis.py','fea_solver.py'):
        source=payload/name
        if _presence(source,payload)!='present_unverified':
            result['reason']='candidate_missing_or_unsafe'
            return result
        try:
            if not 0<source.stat().st_size<4_000_000:
                raise ValueError('bad candidate size')
            tree=ast.parse(source.read_text(encoding='utf8'),filename=name)
        except (OSError,ValueError,UnicodeError,SyntaxError):
            result['reason']='candidate_syntax_or_read_error'
            return result
        for node in tree.body:
            if not isinstance(node,ast.ImportFrom) or not node.module:
                continue
            module_file=node.module.replace('.','/')+'.py'
            if module_file in existing:
                names=required.setdefault(module_file,set())
                # An import * cannot be statically shown safe.
                names.update(alias.name for alias in node.names)
    if not required:
        result['reason']='candidate_has_no_installed_module_imports'
        return result
    invalid=[]
    missing={}
    for module,requested in sorted(required.items()):
        result['required_modules'][module]=sorted(requested)
        path=root.joinpath(*module.split('/'))
        if _presence(path,root)!='present_unverified':
            invalid.append(module)
            continue
        try:
            if not 0<path.stat().st_size<=2_000_000:
                raise ValueError('bad installed module size')
            tree=ast.parse(path.read_text(encoding='utf8'),filename=module)
        except (OSError,UnicodeError,SyntaxError,ValueError):
            invalid.append(module)
            continue
        exports=_declared_top_level_names(tree)
        missing_names=sorted(set(requested)-exports)
        if missing_names:
            missing[module]=missing_names
    result['missing_or_invalid_modules']=invalid
    result['missing_exports']=missing
    result['compatible']=not (invalid or missing)
    result['reason']='static_required_api_present' if result['compatible'] else 'missing_module_or_api'
    return result


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
