"""P5 original L-bracket: the 3D FRD route must not return stale run A.

Synthetic state-only regression of the actual shared production guard, plus an
AST inspection of the existing live field HTTP route. No solver, Windows
runtime, STEP, FEA files, saved reports or SQLite are read or modified.
"""
from __future__ import annotations

import ast
from pathlib import Path
import threading
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "payload" / "GeoField_CAD_Analysis.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)
CAD_ID, CAD_SHA, CASE_SHA = "a" * 32, "b" * 64, "c" * 64
RUN_A, RUN_B = "1" * 32, "2" * 32


def task(rid, state="complete"):
    return {"id": rid, "cad_job_id": CAD_ID, "cad_sha256": CAD_SHA,
            "case_sha256": CASE_SHA, "status": state,
            "result": {"case_sha256": CASE_SHA}}


class LBracketCurrent3DRunTest(unittest.TestCase):
    def setUp(self):
        self.session = {"job_id": CAD_ID, "pending_job_id": CAD_ID,
                        "verified_restored_run_id": None}
        self.jobs = {CAD_ID: {"status": "complete", "sha256": CAD_SHA}}
        self.fea = {RUN_A: task(RUN_A)}
        node = next(x for x in TREE.body if isinstance(x, ast.FunctionDef)
                    and x.name == "qa_report_active_run_unchanged")
        scope = {"CURRENT": self.session, "JOBS": self.jobs,
                 "FEA_JOBS": self.fea, "STATE_LOCK": threading.RLock()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), scope)
        self.guard = scope["qa_report_active_run_unchanged"]

    def test_one_completed_original_run_allowed(self):
        self.assertTrue(self.guard(CAD_ID, CAD_SHA, RUN_A, CASE_SHA))

    def test_newer_same_step_case_prevents_old_3d_even_before_solver_completes(self):
        for state in ("queued", "running", "complete", "failed"):
            with self.subTest(state=state):
                self.fea[RUN_B] = task(RUN_B, state)
                with self.assertRaisesRegex(ValueError, "최신 FEA 실행"):
                    self.guard(CAD_ID, CAD_SHA, RUN_A, CASE_SHA)
                if state == "complete":
                    self.assertTrue(self.guard(CAD_ID, CAD_SHA, RUN_B, CASE_SHA))
                self.fea.pop(RUN_B)

    def test_explicit_saved_run_reopen_stays_supported(self):
        self.fea[RUN_B] = task(RUN_B)
        self.session["verified_restored_run_id"] = RUN_A
        self.assertTrue(self.guard(CAD_ID, CAD_SHA, RUN_A, CASE_SHA))
        with self.assertRaisesRegex(ValueError, "최신 FEA 실행"):
            self.guard(CAD_ID, CAD_SHA, RUN_B, CASE_SHA)

    def test_live_frd_route_calls_guard_after_reverification_before_response(self):
        handler = next(x for x in TREE.body if isinstance(x, ast.ClassDef) and x.name == "Handler")
        method = next(x for x in handler.body
                      if isinstance(x, ast.FunctionDef) and x.name == "do_GET")
        body = ast.unparse(method)
        start = body.index("if path.startswith('/api/fea/field/'):")
        end = body.index("if path.startswith('/api/fea/previous_overview/'):", start)
        field_route = body[start:end]
        self.assertIn("verify_directory(folder, case, result['cad_sha256'])", field_route)
        self.assertIn("qa_report_active_run_unchanged(active, job['sha256'], rid, case['case_sha256'])", field_route)
        self.assertIn("return self.fail('3D 활성 FEA 실행 검증 실패:", field_route)
        self.assertLess(field_route.index("verify_directory("),
                        field_route.index("qa_report_active_run_unchanged("))
        self.assertLess(field_route.index("qa_report_active_run_unchanged("),
                        field_route.index("return self.send_raw(payload)"))


if __name__ == "__main__":
    unittest.main()
