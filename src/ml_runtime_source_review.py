# -*- coding: utf-8 -*-
"""Local-only BrepMFR source inventory. Safe to ship; does not execute ML.

Only explicitly scoped Python source files are bundled for PRIVATE manual
review. The checkpoint is SHA-256 *fingerprinted only*, never copied into
the archive. Do not upload this ZIP or publish its sources without review.
No installed source, CAD, SQLite, solver file, model or Python env is changed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

RUNTIME_ID = "8a9ac53a821a0eb5"
CKPT = "ml/weights/best-epoch43-f1_0.8626.ckpt"
CKPT_SHA256 = "50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1"
MAX_SOURCE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_SOURCES = 64
MAX_CKPT_BYTES = 2_000_000_000
FIXED_SOURCE = ("ml/brepmfr_worker.py", "ml/brepmfr_core/compare_preprocessing.py")
ROOT_PREFIX = "ml/brepmfr_core/"


def default_runtime():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise ValueError("LOCALAPPDATA is unavailable; use --runtime")
    return Path(local) / "GeoFieldCAD" / "onefile_runtime" / RUNTIME_ID


def default_output():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path.home() / "Downloads" / ("GeoField_ML_Source_Review_" + stamp + "_" +
                                       str(os.getpid()) + ".zip")


def _symlink_free(root, p):
    """Check every path component beneath the runtime, including a dangling link."""
    try:
        relative = p.relative_to(root)
    except ValueError:
        return False
    cursor = root
    if cursor.is_symlink():
        return False
    for part in relative.parts:
        if part in (".", "..") or not part or part.startswith("."):
            return False
        cursor = cursor / part
        if cursor.is_symlink():
            return False
    return True


def _read_allowed_source(root, rel):
    p = root.joinpath(*rel.split("/"))
    if not _symlink_free(root, p):
        return None, "unsafe_path_or_symlink"
    try:
        if not p.is_file():
            return None, "missing"
        size = p.stat().st_size
        if size <= 0 or size > MAX_SOURCE_BYTES:
            return None, "empty_or_oversized"
        raw = p.read_bytes()
        if len(raw) != size or b"\x00" in raw:
            return None, "changed_or_non_source"
        # Only files plausibly containing source code; no arbitrary content.
        compile(raw, rel, "exec")
        return raw, "source_unverified"
    except (OSError, SyntaxError, UnicodeError, ValueError):
        return None, "unreadable_or_invalid_python"


def _checkpoint_fingerprint(root):
    path = root.joinpath(*CKPT.split("/"))
    if not _symlink_free(root, path):
        return {"status": "unsafe_path_or_symlink"}
    try:
        if not path.is_file():
            return {"status": "missing"}
        size = path.stat().st_size
        if size <= 0 or size > MAX_CKPT_BYTES:
            return {"status": "empty_or_oversized", "bytes": size}
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        return {"status": ("matches_known_research_checkpoint"
                           if actual == CKPT_SHA256 else "unknown_checkpoint_hash"),
                "bytes": size, "sha256": actual}
    except OSError:
        return {"status": "unreadable"}


def collect(runtime, output):
    """Create a local private review ZIP; no source import or network usage."""
    root = Path(runtime).absolute()
    target = Path(output).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("GeoField installed runtime is absent or unsafe")
    if target == root or root in target.parents:
        raise ValueError("Output cannot be written inside the installed runtime")
    if target.exists():
        raise FileExistsError("Refusing to overwrite an existing review archive")
    # Nonrecursive source review scope: only known BrepMFR worker/core.
    core = root / "ml" / "brepmfr_core"
    names = set(FIXED_SOURCE)
    if core.is_dir() and _symlink_free(root, core):
        for path in core.rglob("*.py"):
            relative = path.relative_to(root).as_posix()
            if (relative.startswith(ROOT_PREFIX) and
                all(not part.startswith(".") for part in path.relative_to(root).parts)):
                names.add(relative)
            if len(names) > MAX_SOURCES:
                raise ValueError("Too many BrepMFR Python files; manual review needed")
    recovered, rejected = {}, {}
    size_total = 0
    for rel in sorted(names):
        if not rel.startswith(ROOT_PREFIX) and rel != FIXED_SOURCE[0]:
            raise ValueError("Unsafe source path outside fixed BrepMFR scope")
        raw, state = _read_allowed_source(root, rel)
        if raw is None:
            rejected[rel] = state
            continue
        size_total += len(raw)
        if size_total > MAX_TOTAL_BYTES:
            raise ValueError("BrepMFR source exceeds review size limit")
        recovered[rel] = raw
    manifest = {
        "schema": "geofield-ml-private-source-inventory-v1",
        "status": "LOCAL_UNTRUSTED_SOURCE_REVIEW_NOT_A_MODEL_VALIDATION",
        "checkpoint": _checkpoint_fingerprint(root),
        "required_sources": list(FIXED_SOURCE),
        "source_hashes": {n:hashlib.sha256(raw).hexdigest()
                          for n,raw in sorted(recovered.items())},
        "source_bytes": {n:len(raw) for n,raw in sorted(recovered.items())},
        "rejected_or_missing": rejected,
        "can_review_worker_source": all(n in recovered for n in FIXED_SOURCE),
        "original_files_changed": False,
        "scope": "BrepMFR .py only; NO checkpoint, STEP, SQLite, FRD, secrets or network",
        "warning": ("ZIP contains PRIVATE unknown Python code. Review for secrets,"
                    " paths, copyright and license before sharing. SHA is not proof"
                    " of authenticity or correctness. No model was executed."),
    }
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                dir=target.parent,prefix=".geofield_ml_",
                suffix=".zip.tmp",delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary,"w",zipfile.ZIP_DEFLATED) as archive:
            for name,raw in sorted(recovered.items()):
                archive.writestr("source/" + name,raw)
            archive.writestr("review_manifest.json",
                json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True).encode("utf-8"))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Review ZIP CRC verification failed")
            for name,digest in manifest["source_hashes"].items():
                if hashlib.sha256(archive.read("source/"+name)).hexdigest() != digest:
                    raise RuntimeError("Review ZIP source hash mismatch")
        created = False
        try:
            with target.open("xb") as dest:
                created = True
                with temporary.open("rb") as src:
                    shutil.copyfileobj(src,dest)
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
        return manifest
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime",type=Path,default=None)
    parser.add_argument("--output",type=Path,default=None)
    args=parser.parse_args(argv)
    try:
        root=args.runtime or default_runtime()
        dest=args.output or default_output()
        report=collect(root,dest)
    except (OSError,ValueError,RuntimeError) as exc:
        print("[BLOCKED] ML review: "+str(exc))
        return 2
    print("[LOCAL PRIVATE ZIP] "+str(dest))
    print("[BREPMFR SOURCES] "+str(len(report["source_hashes"]))+
          " / expected minimum "+str(len(FIXED_SOURCE)))
    print("[BrepMFR CHECKPOINT] "+report["checkpoint"]["status"])
    if report["rejected_or_missing"]:
        print("[MISSING OR UNSAFE] "+", ".join(report["rejected_or_missing"]))
    print("[PRIVACY] No network/upload. Review ZIP content before sharing.")
    return 0 if report["can_review_worker_source"] else 3


if __name__=="__main__":
    raise SystemExit(main())
