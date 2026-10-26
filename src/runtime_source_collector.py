# -*- coding: utf-8 -*-
"""Read-only, allowlisted recovery inventory for an existing GeoField runtime.

This is NOT a new installer or a standalone release. Only the runtime's known
Python source modules are copied to a LOCAL review ZIP. No network, imports of
the recovered sources, package installation, CAD/FEA operations, or file deletion.
The archive must be reviewed before any source is published or integrated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

from runtime_preflight import EXISTING_REQUIRED

MAX_MODULE_BYTES = 2_000_000


def default_runtime():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise ValueError("Windows LOCALAPPDATA unavailable; specify --runtime")
    return Path(local) / "GeoFieldCAD" / "onefile_runtime" / "8a9ac53a821a0eb5"


def default_output():
    name = "GeoField_Runtime_Source_Review_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(os.getpid()) + ".zip"
    return Path.home() / "Downloads" / name


def _safe_module(root, relative):
    """Only allow explicitly named regular files in the runtime, not links."""
    p = PurePosixPath(relative)
    if p.is_absolute() or ".." in p.parts or p.suffix != ".py":
        return None, "invalid_allowlist_path"
    path = root.joinpath(*p.parts)
    if any(part.is_symlink() for part in (root, *list(path.parents)[:-1], path)):
        return None, "symlink_refused"
    if not path.is_file():
        return None, "missing"
    try:
        size = path.stat().st_size
        if not 0 < size <= MAX_MODULE_BYTES:
            return None, "empty_or_oversized"
        data = path.read_bytes()
        if len(data) != size or b"\x00" in data:
            return None, "changed_or_non_source"
        return data, "unverified_local_source"
    except OSError:
        return None, "unreadable"


def collect(runtime, destination):
    """Inventory known code without ever mutating the installed runtime."""
    root = Path(runtime).absolute()
    output = Path(destination).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Existing GeoField runtime directory is missing or unsafe")
    if output == root or root in output.parents:
        raise ValueError("Review ZIP must not be placed inside the installed runtime")
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing review ZIP: " + output.name)
    output.parent.mkdir(parents=True, exist_ok=True)

    allow = tuple(EXISTING_REQUIRED)
    if len(set(allow)) != len(allow):
        raise ValueError("Duplicate runtime source allowlist entry")
    recovered = {}
    missing = {}
    for rel in allow:
        data, state = _safe_module(root, rel)
        if data is None:
            missing[rel] = state
        else:
            recovered[rel] = data

    manifest = {
        "schema": "geofield-local-runtime-source-review-v1",
        "status": "LOCAL_SOURCE_ONLY_NOT_AUTHENTICATED",
        "complete": not missing,
        "expected_source_modules": len(allow),
        "recovered_source_modules": len(recovered),
        "sha256": {key: hashlib.sha256(data).hexdigest() for key, data in sorted(recovered.items())},
        "missing_or_rejected": dict(sorted(missing.items())),
        "scope": "allowlisted Python source only; no STEP, SQLite, FEA results, weights, or credentials requested",
        "warning": "Review recovered Python files for secrets, paths, licenses and compatibility before publishing. Hashes are fingerprints, not authenticity proof.",
    }
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".geofield_review_", suffix=".zip.tmp", dir=output.parent, delete=False) as f:
            temp_path = Path(f.name)
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(recovered.items()):
                archive.writestr("source/" + name, data)
            archive.writestr("review_manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
        with zipfile.ZipFile(temp_path, "r") as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Review archive CRC check failed")
            for name, digest in manifest["sha256"].items():
                if hashlib.sha256(archive.read("source/" + name)).hexdigest() != digest:
                    raise RuntimeError("Review archive source SHA-256 mismatch: " + name)
        # Exclusive write: never overwrite an existing output, even on a race.
        try:
            with output.open("xb") as target, temp_path.open("rb") as source:
                shutil.copyfileobj(source, target)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return manifest
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=None, help="Existing trusted GeoField runtime directory")
    parser.add_argument("--output", type=Path, default=None, help="New ZIP path outside runtime (must not already exist)")
    args = parser.parse_args(argv)
    try:
        runtime = args.runtime or default_runtime()
        output = args.output or default_output()
        result = collect(runtime, output)
    except (OSError, ValueError, RuntimeError) as exc:
        print("[BLOCKED] Runtime source review: " + str(exc))
        return 2
    print("[LOCAL REVIEW ONLY] " + str(output))
    print("[SOURCE MODULES] " + str(result["recovered_source_modules"]) + "/" + str(result["expected_source_modules"]))
    if result["missing_or_rejected"]:
        print("[INCOMPLETE] Missing/blocked: " + ", ".join(result["missing_or_rejected"]))
    else:
        print("[COMPLETE FILE INVENTORY] Source compatibility and legitimacy still require review.")
    print("[PRIVACY] ZIP stays on this PC. It is not uploaded to GitHub or any service.")
    return 0 if result["complete"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
