"""GeoField QA report gate: never turn missing tests into success."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import qa_gate as qa


class OfflineGateTests(unittest.TestCase):
    def fake(self, rc=0, output="Ran 3 tests in 0.01s\nOK", err=""):
        def run(command, **kwargs):
            self.assertIsInstance(command, list)
            self.assertFalse(kwargs.get("shell", False))
            self.assertTrue(Path(kwargs["cwd"]).is_absolute())
            return SimpleNamespace(returncode=rc, stdout=output, stderr=err)
        return run

    def one(self, ident="python_b"):
        return next(x for x in qa.suites("b") if x.id == ident)

    def test_fixed_allowlist_and_scope(self):
        b=qa.suites("b")
        ab=qa.suites("ab")
        self.assertEqual(len(set(s.id for s in b)),len(b))
        self.assertEqual({s.id for s in ab}-{s.id for s in b},
                         {"python_a_fea","candidate_install"})
        with self.assertRaises(ValueError):
            qa.suites("exec arbitrary code")

    def test_python_success_must_run_at_least_one_case(self):
        report=qa.execute(self.one(),runner=self.fake())
        self.assertEqual(report["status"],"passed")
        self.assertEqual(report["test_count"],3)
        zero=qa.execute(self.one(),runner=self.fake(output="Ran 0 tests in 0.01s\nOK"))
        self.assertEqual(zero["status"],"failed")

    def test_node_success_requires_exact_pass_counter(self):
        report=qa.execute(self.one("fea_mesh_label"),runner=self.fake(output="PASS: 13 verified cases"))
        self.assertEqual(report["status"],"passed")
        self.assertEqual(report["test_count"],13)
        empty=qa.execute(self.one("fea_mesh_label"),runner=self.fake(output="No assertions executed"))
        self.assertEqual(empty["status"],"failed")

    def test_failure_with_green_message_cannot_pass(self):
        r=qa.execute(self.one(),runner=self.fake(rc=1,output="Ran 4 tests\nOK",
                                                 err="synthetic assertion failure"))
        self.assertEqual(r["status"],"failed")
        self.assertEqual(r["exit_code"],1)
        self.assertIn("synthetic assertion failure",r["message"])

    def test_skips_are_explicit_not_hidden(self):
        r=qa.execute(self.one(),runner=self.fake(
            output="Ran 95 tests in 0.4s\nOK (skipped=7)"))
        self.assertEqual(r["status"],"passed_with_skips")
        self.assertEqual(r["test_count"],95)
        self.assertEqual(r["skipped_count"],7)

    def test_timeout_and_missing_runner_fail(self):
        import subprocess
        def timeout(*a,**k):
            raise subprocess.TimeoutExpired(a[0],10)
        self.assertEqual(qa.execute(self.one(),runner=timeout)["status"],"failed")
        def missing(*a,**k):
            raise FileNotFoundError("node absent")
        self.assertEqual(qa.execute(self.one("ml_display"),runner=missing)["status"],"failed")

    def test_full_report_keeps_failed_suites_and_no_real_solver_claim(self):
        ids=set()
        def simulate(item):
            ids.add(item.id)
            return {"suite":item.id,
                    "domain":item.domain,
                    "status":"failed" if item.id=="fea_mesh_label" else
                             ("passed_with_skips" if item.id=="python_b" else "passed"),
                    "test_count":7,
                    "skipped_count":1 if item.id=="python_b" else 0}
        r=qa.make_report("b",executor=simulate)
        self.assertEqual(len(ids),len(qa.suites("b")))
        self.assertEqual(r["conclusion"],"failed")
        self.assertEqual(r["failed_suites"],["fea_mesh_label"])
        self.assertEqual(r["skipped_suites"],["python_b"])
        self.assertFalse(r["three_mesh_convergence_certified"])
        self.assertFalse(r["production_release_approved"])
        self.assertEqual(r["actual_calculix_run"],"NOT_TESTED")
        self.assertEqual(r["final_windows_e2e"],"NOT_TESTED")

    def test_json_report_atomic_write_and_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"reports"/"qa.json"
            data={"schema":"test","conclusion":"failed","failed_suites":["a"]}
            qa.write_report(data,target)
            self.assertEqual(json.loads(target.read_text(encoding="utf8")),data)
            self.assertEqual(list(target.parent.iterdir()),[target])
            with self.assertRaises(FileExistsError):
                qa.write_report({"conclusion":"passed"}, target)
            self.assertEqual(json.loads(target.read_text(encoding="utf8")), data)

    def test_all_success_with_skips_is_not_fully_green(self):
        def simulate(item):
            return {"suite":item.id,"domain":item.domain,
                    "status":"passed_with_skips" if item.id=="python_a_fea" else "passed",
                    "test_count":8, "skipped_count":7 if item.id=="python_a_fea" else 0}
        report=qa.make_report("ab",executor=simulate)
        self.assertEqual(report["conclusion"],"passed_with_skips")
        self.assertFalse(report["production_release_approved"])
        self.assertEqual(report["total_test_cases_skipped"],7)
        self.assertEqual(report["total_test_cases_discovered"],len(qa.suites("ab"))*8)
        self.assertEqual(report["total_test_cases_executed"],len(qa.suites("ab"))*8-7)

if __name__ == "__main__":
    unittest.main()
