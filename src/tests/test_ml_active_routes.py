"""Execute the exact ML GET API route AST without importing private CAD/FEA deps.

The test runs real production route bodies, result selector and ML evidence
validator; only HTTP transport and in-memory CAD job state are simulated.
It never claims a full Windows installed GUI/server test.
"""
import ast
import importlib.util
from pathlib import Path
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "payload" / "GeoField_CAD_Analysis.py"
CONTRACT = ROOT / "payload" / "ml_evidence.py"
spec = importlib.util.spec_from_file_location("selected_ml_evidence", CONTRACT)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
CID, OTHER = "a" * 32, "b" * 32
SHA, FOREIGN_SHA = "c" * 64, "d" * 64
BREP = "1" * 32
R12 = "2" * 32
MODEL = "f" * 64


def load_actual_get_routes():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    methods = [n for n in ast.walk(tree) if
               isinstance(n, ast.FunctionDef) and n.name == "do_GET"]
    if len(methods) != 1:
        raise AssertionError("Expected a single production GET handler")
    nodes = []
    for node in ast.walk(methods[0]):
        if not isinstance(node, ast.If):
            continue
        cond = node.test
        if not (isinstance(cond, ast.Call) and isinstance(cond.func, ast.Attribute)
                and cond.func.attr == "startswith" and len(cond.args) == 1):
            continue
        arg = cond.args[0]
        if isinstance(arg, ast.Constant) and arg.value in (
            "/api/ml/evidence/", "/api/ml/latest/"):
            nodes.append(node)
    if len(nodes) != 2:
        raise AssertionError("Original ML GET routes not both found")
    definition = ast.FunctionDef(
        name="route", args=ast.arguments(posonlyargs=[],
            args=[ast.arg(arg="self"), ast.arg(arg="path")],
            vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
        body=sorted(nodes, key=lambda n:n.lineno) + [
            ast.Return(value=ast.Constant(value=None))],
        decorator_list=[], returns=None, type_comment=None)
    result = ast.fix_missing_locations(ast.Module(body=[definition], type_ignores=[]))
    return compile(result, str(SERVER), "exec")


class Response:
    def send_raw(self, data):
        return data
    def fail(self, message, code=400):
        return {"error": message, "status_code": code}


def r12_result():
    return {
        "cad_sha256": SHA,
        "status": "research_not_for_production",
        "decision_usage": "blocked_diagnostic_only",
        "is_independent_r12_research": True,
        "geometry_certified": False,
        "fea_calculated": False,
        "candidate_count": 1,
        "predictions": [{
            "face_index": 4,
            "predicted_hole_type": "unverified",
            "uncalibrated_model_score": 0.6,
            "status": "research_unverified",
            "decision_basis": "insufficient_brep_evidence",
        }],
    }


def ml_task(run_id, provider, status, sha=SHA):
    task = {"id": run_id, "cad_job_id": CID, "cad_sha256": sha,
            "status": status, "automatic": True}
    if status == "complete":
        task["result"] = (
            r12_result() if provider == "r12" else
            {"sha256": SHA, "decision_usage": "blocked_diagnostic_only",
             "variants": {"topology_trimmed": {"faces": []}}}
        )
    return task


class RouteSelection(unittest.TestCase):
    def setUp(self):
        self.job = {"id": CID, "sha256": SHA, "status": "complete",
                    "auto_ml_enabled": True, "auto_ml_status": "complete",
                    "auto_ml_run_id": R12, "auto_ml_provider": "r12"}
        self.brep = {BREP: ml_task(BREP, "brepmfr", "failed")}
        self.research = {R12: ml_task(R12, "r12", "complete")}
        self.current = {"job_id": CID}
        scope = {
            "STATE_LOCK": threading.RLock(), "JOBS": {CID: self.job},
            "ML_JOBS": self.brep, "R12_JOBS": self.research,
            "CURRENT": self.current,
            "valid_uid": lambda value: isinstance(value, str) and
                len(value) == 32 and all(c in "0123456789abcdef" for c in value),
            "ml_select_current_task": evidence.select_current_task,
            "ml_build_evidence": evidence.build_evidence,
            "BREPMFR_SHA256": MODEL,
            "ml_r12_bridge": type("Bridge", (), {"EXPECTED_MODEL_SHA256": MODEL}),
        }
        exec(load_actual_get_routes(), scope)
        self.route = scope["route"]
        self.handler = Response()

    def latest(self, cid=CID):
        return self.route(self.handler, "/api/ml/latest/" + cid)

    def agent(self, cid=CID):
        return self.route(self.handler, "/api/ml/evidence/" + cid)

    def test_recovery_success_beats_failed_brepmfr(self):
        self.assertEqual(self.latest()["provider"], "r12")
        e = self.agent()
        self.assertEqual(e["provider"], "r12")
        self.assertEqual(e["status"], "complete")
        self.assertEqual(len(e["predictions"]), 1)
        self.assertFalse(e["eligible_for_structural_decision"])

    def test_queued_r12_never_returns_old_failure(self):
        self.research[R12] = ml_task(R12, "r12", "queued")
        self.assertEqual(self.latest()["status"], "queued")
        e = self.agent()
        self.assertEqual((e["provider"], e["status"]), ("r12", "queued"))
        self.assertEqual(e["predictions"], [])

    def test_failed_r12_is_not_a_success_for_agent(self):
        self.research[R12] = ml_task(R12, "r12", "failed")
        self.assertEqual(self.latest()["status"], "failed")
        e = self.agent()
        self.assertEqual(e["status"], "failed")
        self.assertEqual(e["predictions"], [])

    def test_absent_selected_run_never_uses_history(self):
        self.job["auto_ml_run_id"] = "3" * 32
        self.job["auto_ml_status"] = "queued"
        self.assertEqual(self.latest()["status"], "queued")
        self.assertEqual(self.agent()["status"], "not_run")
        self.assertEqual(self.agent()["predictions"], [])

    def test_foreign_sha_cannot_reuse_selected_success(self):
        self.research[R12]["cad_sha256"] = FOREIGN_SHA
        self.job["auto_ml_status"] = "recovering"
        self.assertEqual(self.latest()["status"], "running")
        self.assertEqual(self.agent()["status"], "not_run")

    def test_brepmfr_current_over_old_r12(self):
        self.job["auto_ml_run_id"] = BREP
        self.brep[BREP] = ml_task(BREP, "brepmfr", "complete")
        self.assertEqual(self.latest()["provider"], "brepmfr")
        self.assertEqual(self.agent()["provider"], "brepmfr")
        self.assertEqual(self.agent()["predictions"], [])

    def test_model_missing_not_labeled_not_run(self):
        self.brep.clear()
        self.research.clear()
        self.job["auto_ml_status"] = "unavailable"
        self.job["auto_ml_message"] = "R12 Python dependencies missing"
        e = self.agent()
        self.assertEqual(e["status"], "unavailable")
        self.assertEqual(e["provider"], "none")
        self.assertEqual(e["predictions"], [])
        self.assertIn("dependencies", e["message"])

    def test_foreign_cad_get_requests_rejected(self):
        self.assertEqual(self.latest(OTHER)["status_code"], 409)
        self.assertEqual(self.agent(OTHER)["status_code"], 409)


if __name__ == "__main__":
    unittest.main()
