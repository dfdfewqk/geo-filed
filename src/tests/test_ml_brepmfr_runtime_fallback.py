"""Regression: automatic BrepMFR worker failure -> safe research R12 fallback.

Uses the actual GeoField execute_ml, launch_automatic_r12 and execute_r12
functions. Worker subprocess and optional model are simulated. No claim of
genuine BrepMFR inference; real STEP/R12 CI is tested separately.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "payload" / "GeoField_CAD_Analysis.py"


class DeferredThread:
    started = []
    def __init__(self, target, args, daemon):
        if daemon is not True:
            raise AssertionError("ML worker must be a daemon thread")
        self.target, self.args = target, args
    def start(self):
        self.started.append(self)


def _functions():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    names = {"execute_ml", "execute_r12", "launch_automatic_r12"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != names:
        raise AssertionError("Production fallback functions missing")
    return compile(ast.Module(body=nodes, type_ignores=[]), str(SERVER), "exec")


class AutomaticWorkerFallback(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="geofield-ml-fallback-")
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.input = self.dir / "ml_private_copy.step"
        self.original = self.dir / "original.step"
        self.original.write_bytes(b"immutable owner CAD")
        self.input.write_bytes(b"valid private STEP copy bytes")
        self.sha = hashlib.sha256(self.input.read_bytes()).hexdigest()
        self.ckpt = self.dir / "brepmfr.ckpt"
        self.ckpt.write_bytes(b"previously verified fake checkpoint")
        self.model_sha = hashlib.sha256(self.ckpt.read_bytes()).hexdigest()
        self.cid = uuid.uuid4().hex
        self.rid = uuid.uuid4().hex
        self.jobs = {self.cid: {
            "sha256": self.sha, "status": "complete", "auto_ml_enabled": True,
            "auto_ml_run_id": self.rid, "auto_ml_status": "running",
        }}
        self.current = {"job_id": self.cid}
        self.ml = {self.rid: {
            "id": self.rid, "cad_job_id": self.cid, "cad_sha256": self.sha,
            "automatic": True, "status": "queued",
        }}
        self.r12 = {}
        self.archived = []
        self.logs = []
        self.run = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("BrepMFR subprocess crashed"))
        self.r12_available = True
        self.r12_crashes = False
        self.r12_result = {
            "cad_sha256": self.sha,
            "status": "research_not_for_production",
            "decision_usage": "blocked_diagnostic_only",
            "geometry_certified": False, "fea_calculated": False,
            "is_independent_r12_research": True,
            "candidate_count": 0, "predictions": [],
        }
        self.bridge = SimpleNamespace(
            EXPECTED_MODEL_SHA256="f" * 64,
            locations=lambda root: (_ for _ in ()).throw(OSError("no frozen checkpoint for restoration")),
            validate_research_result=lambda *a: None,
            preflight=lambda root: {
                "available": self.r12_available,
                "missing": [] if self.r12_available else ["R12 modules missing"],
            },
            execute=self._r12_execute,
        )
        self.store = SimpleNamespace(
            restore_latest=lambda *a: None,
            persist=lambda *a: {
                "completed_at": "2026-10-22T00:00:00+00:00",
                "model_version": "r12-research-" + "f" * 12,
                "model_sha256": "f" * 64,
            },
        )
        self.ns = {
            "JOBS_DIR": self.dir, "ROOT": self.dir,
            "STATE_LOCK": threading.RLock(), "JOBS": self.jobs,
            "CURRENT": self.current, "ML_JOBS": self.ml, "R12_JOBS": self.r12,
            "BREPMFR_SHA256": self.model_sha, "REQUIRED_ML": ("torch",),
            "file_sha256": lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest(),
            "Path": Path, "shutil": shutil, "uuid": uuid, "json": json, "os": os,
            "threading": SimpleNamespace(Thread=DeferredThread),
            "subprocess": SimpleNamespace(
                run=lambda *a, **kw: self.run(*a, **kw), CREATE_NO_WINDOW=0),
            "prepare_python_environment": lambda p: {},
            "resolve_ml_python": lambda *a: {"ok": True, "path": "preverified-python"},
            "qa_validate_brepmfr_diagnostic": lambda data, sha: data,
            "archive_current_job": lambda cid, kind: self.archived.append((cid, kind)),
            "ml_r12_bridge": self.bridge, "ml_r12_store": self.store,
        }
        exec(_functions(), self.ns)
        DeferredThread.started = []

    def _r12_execute(self, *args):
        if self.r12_crashes:
            raise RuntimeError("R12 model failed")
        return dict(self.r12_result)

    def _invoke(self):
        self.ns["execute_ml"](self.rid, self.cid, self.input, self.ckpt)
        self.assertFalse(self.input.exists())
        self.assertEqual(self.original.read_bytes(), b"immutable owner CAD")
        self.assertEqual(self.jobs[self.cid]["status"], "complete")

    def test_worker_crash_queues_r12_and_final_completion(self):
        self._invoke()
        self.assertEqual(self.ml[self.rid]["status"], "failed")
        self.assertEqual(len(DeferredThread.started), 1)
        fallback = self.ml[self.rid]["fallback_run_id"]
        self.assertNotEqual(fallback, self.rid)
        self.assertEqual(self.jobs[self.cid]["auto_ml_run_id"], fallback)
        self.assertEqual(self.jobs[self.cid]["auto_ml_status"], "queued")
        self.assertEqual(self.r12[fallback]["provider"], "r12")
        self.assertEqual(self.archived, [(self.cid, "ml_failed")])
        thread = DeferredThread.started.pop()
        thread.target(*thread.args)
        self.assertEqual(self.r12[fallback]["status"], "complete")
        self.assertEqual(self.jobs[self.cid]["auto_ml_status"], "complete")
        self.assertEqual(self.ml[self.rid]["status"], "failed")

    def test_failed_r12_retains_failure_without_touching_cad(self):
        self.r12_crashes = True
        self._invoke()
        thread = DeferredThread.started.pop()
        thread.target(*thread.args)
        fallback = self.ml[self.rid]["fallback_run_id"]
        self.assertEqual(self.r12[fallback]["status"], "failed")
        self.assertEqual(self.jobs[self.cid]["auto_ml_status"], "failed")

    def test_r12_unavailable_reports_diagnostic_and_no_new_worker(self):
        self.r12_available = False
        self._invoke()
        self.assertEqual(self.jobs[self.cid]["auto_ml_status"], "unavailable")
        self.assertIn("R12 modules missing", self.jobs[self.cid]["auto_ml_message"])
        self.assertEqual(len(DeferredThread.started), 0)

    def test_manual_brepmfr_failure_never_launches_r12(self):
        self.ml[self.rid]["automatic"] = False
        self._invoke()
        self.assertEqual(self.ml[self.rid]["status"], "failed")
        self.assertEqual(len(DeferredThread.started), 0)

    def test_disabled_auto_ml_never_launches_r12(self):
        self.jobs[self.cid]["auto_ml_enabled"] = False
        self._invoke()
        self.assertEqual(len(DeferredThread.started), 0)

    def test_switched_cad_never_launches_r12(self):
        self.current["job_id"] = uuid.uuid4().hex
        self._invoke()
        self.assertEqual(len(DeferredThread.started), 0)
        self.assertEqual(self.jobs[self.cid]["auto_ml_run_id"], self.rid)

    def test_changed_ml_copy_never_launches_r12(self):
        self.input.write_bytes(b"changed STEP after job creation")
        self._invoke()
        self.assertEqual(len(DeferredThread.started), 0)
        self.assertEqual(self.jobs[self.cid]["auto_ml_status"], "failed")
        self.assertIn("SHA", self.jobs[self.cid]["auto_ml_message"])

    def test_succeeded_brepmfr_does_not_use_fallback(self):
        data = {
            "sha256": self.sha, "decision_usage": "blocked_diagnostic_only",
            "variants": {"topology_trimmed": {"faces": []}},
        }
        def successful_process(*a, **kw):
            folder = self.dir / "ml_runs" / self.rid
            (folder / "predictions.json").write_text(json.dumps(data), encoding="utf-8")
            return SimpleNamespace(returncode=0,stdout="",stderr="")
        self.run = successful_process
        self._invoke()
        self.assertEqual(self.ml[self.rid]["status"], "complete")
        self.assertEqual(self.ml[self.rid]["result"], data)
        self.assertEqual(len(DeferredThread.started), 0)

    def test_latest_and_evidence_select_recovery_task(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn("ml_select_current_task(uid,source_sha,job.get('auto_ml_run_id')",source)
        self.assertIn("selected=ml_select_current_task(uid,job.get('sha256')",source)
        self.assertIn("if state=='recovering':state='running'",source)


if __name__ == "__main__":
    unittest.main()
