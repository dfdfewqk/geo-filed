"""Real R12 automatic pipeline across worker, persistence and agent evidence.

The public STEP and bundled RandomForest checkpoint are genuinely read by
CadQuery/OCP/scikit-learn in a subprocess. Only unrelated CAD completion state,
the optional unavailable BrepMFR preflight and the private engine-runtime
adapter are simulated. This does NOT certify a full HTTP/Windows GUI/FEA run.
"""
from __future__ import annotations
import ast
import hashlib
import json
import shutil
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from verify_ml_real_r12_ci import PAYLOAD, STEP, ml_r12_bridge
import ml_r12_store
from ml_evidence import build_evidence

SERVER = PAYLOAD / "GeoField_CAD_Analysis.py"
EXPECTED_CAD_SHA = "fe65841074c5fc6bd74442b147e5688490ec1ad79d5fb1e41bdccd3514bccf32"


def _load_production_functions():
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SERVER))
    names = {"launch_automatic_ml", "launch_automatic_r12", "execute_r12"}
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    if {node.name for node in nodes} != names:
        raise RuntimeError("Production ML automatic pipeline functions missing")
    scope = {
        "__builtins__": __builtins__,
        "Path": Path, "json": json, "shutil": shutil,
        "threading": threading, "uuid": uuid,
        "ml_r12_bridge": ml_r12_bridge, "ml_r12_store": ml_r12_store,
        "file_sha256": ml_r12_bridge.sha,
        "ml_preflight": lambda: {
            "available": False,
            "missing": ["BrepMFR optional checkpoint absent (intentional test condition)"],
        },
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SERVER), "exec"), scope)
    return scope


def _wait(scope, run_id, timeout_seconds=190):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with scope["STATE_LOCK"]:
            task = dict(scope["R12_JOBS"].get(run_id) or {})
        if task.get("status") in ("complete", "failed"):
            return task
        time.sleep(.25)
    raise RuntimeError("Actual automatic R12 worker timed out")


def _new_completed_cad(scope, sha):
    cad_id = uuid.uuid4().hex
    job = {"id": cad_id, "sha256": sha, "status": "complete",
           "auto_ml_enabled": True}
    with scope["STATE_LOCK"]:
        scope["CURRENT"]["job_id"] = cad_id
        scope["JOBS"][cad_id] = job
    return cad_id, job


def main():
    if ml_r12_bridge.sha(STEP) != EXPECTED_CAD_SHA:
        raise RuntimeError("Original cross-platform STEP fixture SHA mismatch")
    preflight = ml_r12_bridge.preflight(PAYLOAD)
    if not preflight.get("available"):
        raise RuntimeError("Real inference environment not ready: " + repr(preflight))
    original_bytes = STEP.read_bytes()
    with tempfile.TemporaryDirectory(prefix="geofield-ml-auto-real-") as work:
        root = Path(work)
        scope = _load_production_functions()
        scope.update({
            "ROOT": PAYLOAD, "JOBS_DIR": root,
            "STATE_LOCK": threading.RLock(), "CURRENT": {},
            "JOBS": {}, "ML_JOBS": {}, "R12_JOBS": {},
        })
        cad_id, job = _new_completed_cad(scope, EXPECTED_CAD_SHA)
        first_id = scope["launch_automatic_ml"](cad_id, STEP)
        if not first_id:
            raise RuntimeError("Auto-ML did not start a genuine research worker")
        first = _wait(scope, first_id)
        if first.get("status") != "complete":
            raise RuntimeError("Real automatic ML failed: " + str(first.get("message")))
        if job.get("auto_ml_status") != "complete":
            raise RuntimeError("Parent CAD job was not informed of automatic ML completion")
        if first.get("provider") != "r12" or not first.get("automatic"):
            raise RuntimeError("Automatic BrepMFR fallback did not select R12")
        result = first["result"]
        if result["cad_sha256"] != EXPECTED_CAD_SHA or result["candidate_count"] <= 0:
            raise RuntimeError("Real STEP inference returned no valid research candidates")
        stored = root / "ml_r12_runs" / first_id / "completed.json"
        if not stored.is_file():
            raise RuntimeError("Auto-ML did not persist the verified worker run")
        evidence = build_evidence(
            cad_id, EXPECTED_CAD_SHA, task=first, provider="r12",
            model_sha256=ml_r12_bridge.EXPECTED_MODEL_SHA256,
        )
        if (evidence["status"] != "complete" or
                evidence["eligible_for_structural_decision"] is not False or
                evidence["research_only"] is not True or
                len(evidence["predictions"]) != result["candidate_count"]):
            raise RuntimeError("Automatic agent evidence falsely promotes ML or loses candidates")

        # Simulate user re-importing exactly the same original STEP after
        # restarting: memory job identity changes; same checkpoint/bytes must
        # restore, not launch another expensive worker.
        scope["R12_JOBS"] = {}
        scope["ML_JOBS"] = {}
        new_cad_id, new_job = _new_completed_cad(scope, EXPECTED_CAD_SHA)
        second_id = scope["launch_automatic_ml"](new_cad_id, STEP)
        restored = dict(scope["R12_JOBS"].get(second_id) or {})
        if (restored.get("status") != "complete" or
                restored.get("restored_from_run_id") != first_id or
                restored.get("id") == first_id or
                new_job.get("auto_ml_status") != "complete"):
            raise RuntimeError("Saved result was not restored to new CAD session")
        directories = list((root / "ml_r12_runs").iterdir())
        if len(directories) != 1:
            raise RuntimeError("Result reuse incorrectly launched a second R12 model run")
        restored_evidence = build_evidence(
            new_cad_id, EXPECTED_CAD_SHA, task=restored, provider="r12",
            model_sha256=ml_r12_bridge.EXPECTED_MODEL_SHA256,
        )
        if (restored_evidence["restored_from_run_id"] != first_id or
                restored_evidence["model_version"] != evidence["model_version"] or
                restored_evidence["completed_at"] != evidence["completed_at"]):
            raise RuntimeError("Agent evidence lost verified restored provenance")

        try:
            build_evidence(
                new_cad_id, EXPECTED_CAD_SHA, task=first, provider="r12",
                model_sha256=ml_r12_bridge.EXPECTED_MODEL_SHA256,
            )
        except ValueError:
            pass
        else:
            raise RuntimeError("Old CAD session evidence was wrongly accepted")
        if ml_r12_store.restore_latest(
            root / "ml_r12_runs", "d" * 64,
            ml_r12_bridge.EXPECTED_MODEL_SHA256,
            ml_r12_bridge.validate_research_result,
        ) is not None:
            raise RuntimeError("Stale CAD result was reused")

        if STEP.read_bytes() != original_bytes:
            raise RuntimeError("Original STEP was modified by automatic ML")
        print("ACTUAL_R12_AUTO_PIPELINE=" + json.dumps({
            "status": "passed", "real_model_inference": True,
            "candidate_count": result["candidate_count"],
            "cad_sha256": EXPECTED_CAD_SHA,
            "model_sha256": ml_r12_bridge.EXPECTED_MODEL_SHA256,
            "worker_saved": True,
            "reimport_restored_without_new_worker": True,
            "agent_evidence": "research_only",
            "old_cad_rejected": True, "original_step_preserved": True,
            "full_gui_and_fea_not_tested": True,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
