# -*- coding: utf-8 -*-
"""SHA-gated, append-only archive for completed R12 research inference.

No legacy SQLite, FEA, STEP, or model files are changed.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

SCHEMA = "geofield-r12-completed-v1"
MAX_RESULT_BYTES = 2_000_000
MAX_METADATA_BYTES = 4_096


def _hex(value, size):
    return isinstance(value, str) and len(value) == size and all(
        c in "0123456789abcdef" for c in value
    )


def _checked_result(path, validator, cad_sha256):
    if path.is_symlink() or not path.is_file():
        raise ValueError("R12 result missing or symlink")
    if path.stat().st_size > MAX_RESULT_BYTES:
        raise ValueError("R12 result too large")
    raw = path.read_bytes()
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError("R12 result exceeds size bound")
    result = json.loads(raw)
    validator(result, cad_sha256)
    return raw, result


def persist(run_dir, run_id, cad_sha256, model_sha256, result, validator):
    """Atomically record independently verified worker output for one run."""
    folder = Path(run_dir)
    if not (_hex(run_id, 32) and folder.name == run_id and
            _hex(cad_sha256, 64) and _hex(model_sha256, 64)):
        raise ValueError("Invalid R12 archive identity")
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Invalid R12 archive directory")
    raw, saved = _checked_result(folder / "r12_prediction.json", validator, cad_sha256)
    if saved != result:
        raise ValueError("R12 saved result differs from worker output")
    manifest = folder / "completed.json"
    if manifest.exists() or manifest.is_symlink():
        raise ValueError("R12 archive already exists")
    record = {
        "schema": SCHEMA,
        "run_id": run_id,
        "cad_sha256": cad_sha256,
        "model_sha256": model_sha256,
        "model_version": "r12-research-" + model_sha256[:12],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "result_sha256": hashlib.sha256(raw).hexdigest(),
        "research_only": True,
        "status": "complete",
    }
    scratch = folder / ("completed.json." + uuid.uuid4().hex + ".tmp")
    try:
        with scratch.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        if manifest.exists() or manifest.is_symlink():
            raise ValueError("R12 archive appeared concurrently")
        os.replace(scratch, manifest)
    finally:
        scratch.unlink(missing_ok=True)
    return record


def restore_latest(root, cad_sha256, model_sha256, validator, max_scan=256):
    """Ignore incomplete/tampered runs; only load the same CAD and model."""
    base = Path(root)
    if not (_hex(cad_sha256, 64) and _hex(model_sha256, 64)):
        raise ValueError("Invalid requested R12 archive SHA")
    try:
        if base.is_symlink() or not base.is_dir():
            return None
        candidates = []
        # A denied/stale archive directory must not abort new CAD/ML analysis.
        for folder in base.iterdir():
            try:
                if not _hex(folder.name, 32) or folder.is_symlink() or not folder.is_dir():
                    continue
                manifest = folder / "completed.json"
                if manifest.is_symlink() or not manifest.is_file():
                    continue
                candidates.append((manifest.stat().st_mtime_ns, folder))
            except OSError:
                continue
    except OSError:
        return None
    for _, folder in sorted(candidates, reverse=True)[:max_scan]:
        try:
            manifest = folder / "completed.json"
            if manifest.is_symlink() or manifest.stat().st_size > MAX_METADATA_BYTES:
                continue
            # Bound the read itself: a concurrent writer may change file size.
            with manifest.open("rb") as meta_file:
                meta_raw = meta_file.read(MAX_METADATA_BYTES + 1)
            if len(meta_raw) > MAX_METADATA_BYTES:
                continue
            meta = json.loads(meta_raw.decode("utf-8"))
            if (not isinstance(meta, dict) or meta.get("schema") != SCHEMA or
                    meta.get("status") != "complete" or
                    meta.get("research_only") is not True or
                    meta.get("run_id") != folder.name or
                    meta.get("cad_sha256") != cad_sha256 or
                    meta.get("model_sha256") != model_sha256 or
                    meta.get("model_version") != "r12-research-" + model_sha256[:12] or
                    not isinstance(meta.get("completed_at"), str) or
                    not _hex(meta.get("result_sha256"), 64)):
                continue
            raw, data = _checked_result(folder / "r12_prediction.json", validator, cad_sha256)
            if hashlib.sha256(raw).hexdigest() != meta["result_sha256"]:
                continue
            return {"run_id": meta["run_id"],
                    "completed_at": meta["completed_at"],
                    "model_version": meta["model_version"],
                    "result": data}
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
            continue
    return None
