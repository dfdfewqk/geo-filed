# -*- coding: utf-8 -*-
"""B01 read-only, local-only inventory of EXISTING GeoField Windows source.

Does not install, import installed modules, run CAD/FEA, collect STEP/SQLite,
copy raw Python source, create a ZIP or contact a network service.

Without --output this command prints JSON only. Any Windows installation
must be inspected on that same computer; the repository cannot establish it.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from runtime_preflight import (
    A11_NEW_BACKEND_MODULES,
    EXISTING_REQUIRED,
    FRONTEND_REQUIRED,
    UPDATABLE_REQUIRED_BEFORE_INSTALL,
    audit_backend_import_contract,
    audit_engine_runtime_contract,
    audit_runtime,
)

MAX_SOURCE_BYTES = 2_000_000
MAX_CSS_BYTES = 4_000_000
_VERSION_PATTERN = re.compile(r"v?[0-9][0-9a-zA-Z._+-]{0,39}\Z")


def default_runtime():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise ValueError("LOCALAPPDATA is unavailable; provide --runtime")
    return Path(local) / "GeoFieldCAD" / "onefile_runtime" / "8a9ac53a821a0eb5"


def _parts_safe(root, file):
    """Refuse links under the selected directory. Do not follow unknown paths."""
    if root.is_symlink():
        return False
    path = file
    while path != root:
        if path.is_symlink() or path == path.parent:
            return False
        path = path.parent
    return True


def _version_from_source(source):
    """Only a small literal dotted version is reportable, never arbitrary text."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id in
                   ("__version__", "VERSION", "APP_VERSION") for t in targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            value = node.value.value
            if _VERSION_PATTERN.fullmatch(value):
                return value
    return None


def _file_identity(root, rel, *, python_source=True):
    """Read only fixed, allowlisted local files, never discover user directories."""
    path = root.joinpath(*rel.split("/"))
    if not _parts_safe(root, path):
        return {"status": "unsafe_symlink"}
    try:
        state = path.stat()
    except FileNotFoundError:
        return {"status": "missing"}
    except OSError:
        return {"status": "unreadable"}
    if not stat.S_ISREG(state.st_mode):
        return {"status": "not_regular"}
    maximum = MAX_SOURCE_BYTES if python_source else MAX_CSS_BYTES
    if not 0 < state.st_size <= maximum:
        return {"status": "empty_or_oversized"}
    try:
        raw = path.read_bytes()
        after = path.stat()
    except OSError:
        return {"status": "unreadable"}
    if (len(raw) != state.st_size or
            (state.st_dev, state.st_ino, state.st_mtime_ns, state.st_size) !=
            (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)):
        return {"status": "changed_during_read"}
    result = {"status": "present_unverified", "size_bytes": len(raw),
              "sha256": hashlib.sha256(raw).hexdigest()}
    if python_source:
        if b"\x00" in raw:
            result["status"] = "non_source_data"
            return result
        try:
            source = raw.decode("utf-8-sig")
            ast.parse(source, filename=rel)
        except (SyntaxError, UnicodeError, ValueError):
            result["status"] = "invalid_python"
            return result
        version = _version_from_source(source)
        if version is not None:
            result["literal_version_unverified"] = version
    return result


def inspect_runtime(runtime, candidate_payload=None, source_root=None):
    """B01 inventory. Reports file fingerprints but never installed source text.

    candidate_payload should be the tracked GitHub src/payload folder to
    statically crosscheck imports against the *actual* legacy runtime.
    """
    root = Path(runtime).absolute()
    candidate = Path(candidate_payload).absolute() if candidate_payload else None
    staged = Path(source_root).absolute() if source_root else None
    groups = {
        "existing_installed_private_modules": tuple(EXISTING_REQUIRED),
        "existing_updatable_modules": tuple(UPDATABLE_REQUIRED_BEFORE_INSTALL),
        "existing_frontend_assets": tuple(FRONTEND_REQUIRED),
    }
    all_files = [name for group in groups.values() for name in group]
    if len(set(all_files)) != len(all_files):
        raise ValueError("B01 inventory allowlist overlaps")
    exists = root.is_dir() and not root.is_symlink()
    files = {}
    for category, names in groups.items():
        for name in names:
            files[name] = {"category": category, **_file_identity(
                root, name, python_source=name.endswith(".py"))} if exists else {
                    "category": category, "status": "runtime_unavailable"}
    missing = sorted(k for k, v in files.items() if v["status"] == "missing")
    invalid = sorted(k for k, v in files.items() if v["status"] not in
                     ("present_unverified", "missing"))
    new_source = {}
    for name in A11_NEW_BACKEND_MODULES:
        # Newly authored GitHub helpers are NEVER required in the old runtime.
        # Only check source_root if explicitly provided; otherwise unknown.
        new_source[name] = _file_identity(staged, name) if staged and staged.is_dir() \
            and not staged.is_symlink() else {"status": "source_not_supplied"}
    legacy_presence = audit_runtime(root) if exists else {
        "ready_for_update": False, "runtime_found": False,
        "note": "Not checked: installed directory missing or unsafe"}
    engine = audit_engine_runtime_contract(root) if exists else {
        "status": "not_checked", "compatible": False,
        "reason": "runtime_missing"}
    contract = audit_backend_import_contract(root, candidate) if candidate else {
        "schema": "geofield-installed-source-api-v1",
        "compatible": False, "reason": "candidate_not_supplied",
        "installed_code_executed": False, "solver_executed": False}
    return {
        "schema": "geofield-b01-local-runtime-inventory-v1",
        "runtime_identifier": root.name,
        "runtime_found": bool(exists),
        "read_only": True, "private_source_exported": False,
        "network_used": False, "installed_code_executed": False,
        "solver_executed": False, "model_executed": False,
        "source_authenticity_proven": False, "installed_app_operational": None,
        "inventory": dict(sorted(files.items())),
        "required_installed_count": len(all_files),
        "fingerprinted_count": sum(v["status"] == "present_unverified"
                                 for v in files.values()),
        "missing": missing, "invalid_or_unsafe": invalid,
        "new_github_helpers_not_expected_in_old_runtime": dict(sorted(new_source.items())),
        "legacy_presence_only": {
            "checked": exists,
            "all_listed_files_present": bool(legacy_presence.get("ready_for_update")),
            "note": legacy_presence.get("note")},
        "engine_runtime_static_api": engine,
        "backend_import_static_api": contract,
        "static_source_inventory_complete": bool(
            exists and not missing and not invalid and
            all(x["status"] == "present_unverified" for x in files.values())),
        "safe_to_install_inferred": False,
        "next": ("B01: inspect this local report and installed source contracts. "
                 "B06 owns deployment of the four NEW backend helpers; "
                 "B07 owns final Windows Gmsh/CalculiX/renderer/API tests. "
                 "Never infer source legitimacy or app readiness from SHA alone."),
    }


def _write_optional_report(report, output, runtime):
    """Write a fresh JSON only when expressly requested, never inside runtime."""
    path = Path(output).absolute()
    root = Path(runtime).absolute()
    if path == root or root in path.parents:
        raise ValueError("B01 report output cannot be inside the installed runtime")
    if path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("B01 output directory unavailable or symbolic link")
    wire = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as f:
        f.write(wire)
        f.flush()
        os.fsync(f.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, help="Existing installed runtime path")
    parser.add_argument("--candidate", type=Path,
                        help="Optional GitHub src/payload to check installed API names")
    parser.add_argument("--source-root", type=Path,
                        help="Optional GitHub src folder to inventory NEW B06 helpers")
    parser.add_argument("--output", type=Path,
                        help="Optional NEW JSON path outside runtime; never overwrite")
    args = parser.parse_args(argv)
    try:
        root = args.runtime or default_runtime()
        report = inspect_runtime(root, args.candidate, args.source_root)
        if args.output:
            _write_optional_report(report, args.output, root)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": "geofield-b01-local-runtime-inventory-v1",
                          "status": "blocked",
                          "reason": type(exc).__name__,
                          "read_only_installed_runtime": True}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["static_source_inventory_complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
