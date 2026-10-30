# -*- coding: utf-8 -*-
"""Read-only bridge between a GeoField source checkout and its installed runtime.

GitHub deliberately does not include original Windows CAD/FEA modules.
This developer entry point never installs, copies, or modifies them.
A source checkout is not the distributable GeoField Windows update.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from runtime_preflight import (
    EXISTING_REQUIRED, audit_backend_import_contract,
    audit_engine_runtime_contract, audit_runtime,
)

RUNTIME_ID = "8a9ac53a821a0eb5"
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "payload" / "GeoField_CAD_Analysis.py"


def installed_runtime(localappdata=None):
    local = localappdata if localappdata is not None else os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return Path(local) / "GeoFieldCAD" / "onefile_runtime" / RUNTIME_ID


def _readable_fingerprint(root):
    """Fingerprint installed modules locally; digests alone do not prove origin."""
    fingerprints = {}
    for name in EXISTING_REQUIRED:
        path = root.joinpath(*name.split("/"))
        if path.is_symlink() or not path.is_file():
            return False, name
        try:
            if not 0 < path.stat().st_size <= 2_000_000:
                return False, name
            digest = hashlib.sha256()
            with path.open("rb") as file:
                for block in iter(lambda: file.read(64 * 1024), b""):
                    digest.update(block)
            fingerprints[name] = digest.hexdigest()
        except OSError:
            return False, name
    return True, len(fingerprints)


def inspect(runtime):
    """Never import or execute installed runtime code during audit."""
    report = {"mode": "read_only", "ready": False, "runtime_found": False,
              "checks": {}, "error": "", "next_action": ""}
    if runtime is None:
        report.update(error="LOCALAPPDATA is unset; give --runtime to audit an installed runtime")
        return report
    if runtime.is_symlink() or not runtime.is_dir():
        report.update(error="Installed GeoField runtime folder not found",
                      next_action="Use the installed Windows GeoField launcher; do not create missing modules")
        return report
    report["runtime_found"] = True
    present = audit_runtime(runtime)
    engine = audit_engine_runtime_contract(runtime)
    contract = audit_backend_import_contract(runtime, ROOT / "payload")
    report["checks"] = {
        "required_modules_present": bool(present.get("ready_for_update")),
        "engine_api_compatible_static": bool(engine.get("compatible")),
        "backend_imports_compatible_static": bool(contract.get("compatible")),
    }
    if not report["checks"]["required_modules_present"]:
        report.update(error="Required installed modules missing or unsafe",
                      missing=present.get("missing") or [],
                      invalid=present.get("unsafe") or present.get("empty_or_unreadable") or [])
        return report
    # Directory listings are insufficient; the current user must actually be
    # able to read the private source before an import can be attempted.
    fingerprint_ok, count_or_name = _readable_fingerprint(runtime)
    report["checks"]["installed_sources_readable_and_fingerprinted"] = fingerprint_ok
    if not fingerprint_ok:
        report.update(error="Installed runtime sources cannot be read or fingerprinted",
                      blocked_module=count_or_name,
                      next_action="Run the read-only check in the normal Windows user session")
        return report
    report["fingerprinted_module_count"] = count_or_name
    if not engine.get("compatible"):
        report.update(error="Installed engine_runtime.py does not satisfy required static API",
                      missing_exports=engine.get("missing_exports") or [])
        return report
    if not contract.get("compatible"):
        report.update(error="Installed modules are not statically compatible with source checkout",
                      missing_modules=contract.get("missing_or_invalid_modules") or [],
                      missing_exports=contract.get("missing_exports") or {})
        return report
    report["ready"] = True
    report["next_action"] = "Static preflight passed; --check must still verify real imports and native DLLs"
    return report


def choose_python(localappdata, explicit=None):
    """Only reuse identified installed interpreters; never guess a bare 'python'."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("GEOFIELD_PYTHON"):
        candidates.append(os.environ["GEOFIELD_PYTHON"])
    if localappdata:
        candidates.append(str(Path(localappdata) / "GeoFieldCAD" / "engines" /
                              "geofield-analysis-win64" / "python.exe"))
    if os.environ.get("GEOFIELD_R12_PYTHON"):
        candidates.append(os.environ["GEOFIELD_R12_PYTHON"])
    for candidate in candidates:
        path = Path(candidate.strip().strip('"')).expanduser()
        if path.is_file() and path.name.lower().startswith("python"):
            return path.resolve()
    return None


def run_backend(python, runtime, *, check=True, port=8600):
    if not BACKEND.is_file():
        raise RuntimeError("GitHub backend source is missing")
    if not check:
        with socket.socket() as sock:
            sock.settimeout(0.7)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("Port already occupied; do not terminate an unknown process")
    env = os.environ.copy()
    # Keep the tracked payload source ahead of the private legacy runtime;
    # the installed runtime supplies only missing original dependencies.
    original = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "payload"), str(ROOT), str(runtime)] + ([original] if original else []))
    env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    command = [str(python), "-u", str(BACKEND), "--check" if check else "--port"]
    if not check:
        command += [str(port), "--no-browser"]
    # No shell, no package download and no change to the installed runtime.
    return subprocess.run(command, cwd=str(ROOT / "payload"), env=env,
                          timeout=45 if check else None, check=False).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--audit", action="store_true", help="Read-only audit (default)")
    group.add_argument("--check", action="store_true", help="Run backend --check after audit")
    group.add_argument("--serve", action="store_true", help="Start development backend after audit")
    parser.add_argument("--runtime", type=Path, help="Original installed runtime folder")
    parser.add_argument("--python", dest="python_exe", type=str,
                        help="Explicit already-installed Python interpreter")
    parser.add_argument("--port", type=int, default=8600)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Invalid TCP port")
    runtime = args.runtime or installed_runtime()
    try:
        report = inspect(runtime)
    except (OSError, ValueError) as exc:
        report = {"mode": "read_only", "ready": False,
                  "error": "Runtime inspection failed: " + type(exc).__name__}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    if not report["ready"]:
        return 24
    if not (args.check or args.serve):
        return 0
    python = choose_python(os.environ.get("LOCALAPPDATA"), args.python_exe)
    if python is None:
        print("[BLOCKED] No identified GeoField Python executable; use --python PATH", file=sys.stderr)
        return 25
    try:
        return run_backend(python, runtime, check=args.check, port=args.port)
    except subprocess.TimeoutExpired:
        print("[BLOCKED] Backend import/check timed out", file=sys.stderr)
    except OSError as exc:
        print("[BLOCKED] Backend Python could not start: " + type(exc).__name__, file=sys.stderr)
    except RuntimeError as exc:
        print("[BLOCKED] " + str(exc), file=sys.stderr)
    return 26


if __name__ == "__main__":
    raise SystemExit(main())
