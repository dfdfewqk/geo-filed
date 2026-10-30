"""Real source process_job regression: both opted-in classifiers run independently.

Executes only the AST-extracted CAD process function with disposable synthetic
STEP bytes. No FreeCAD, CAD process, live ML, CalculiX, network or paid LLM.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "payload" / "GeoField_CAD_Analysis.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
FN = next(x for x in TREE.body if isinstance(x, ast.FunctionDef) and x.name == "process_job")
ID = "a" * 32
SHA = "b" * 64


class AutomaticResearchOnImport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-auto-r12-import-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / "freecad_export.FCMacro").write_text("__GEOFIELD_CONFIG_JSON__", encoding="utf8")
        self.data = self.base / "jobs"
        self.data.mkdir()
        self.step = self.data / (ID + ".step")
        self.step.write_bytes(b"ISO-10303-21; synthetic disposable test input")
        self.calls = []
        self.jobs = {ID: {"id": ID, "status": "queued", "sha256": SHA,
                          "auto_ml_enabled": True}}
        self.current = {"pending_job_id": ID}
        self.raise_r12 = False
        self.raise_brep = False

        def set_job(uid, **values):
            self.jobs[uid].update(values)

        def run_freecad_analysis(job, script_path, output_path, *_rest):
            output_path.write_text('{"sha256": "' + SHA + '"}', encoding="utf8")

        def r12(uid, path):
            self.calls.append(("r12", uid, path.read_bytes()))
            if self.raise_r12:
                raise OSError("disposable R12 worker failure")
            if not self.jobs[uid].get("auto_ml_enabled"):
                return None
            self.jobs[uid]["auto_r12_status"] = "queued"
            return "1" * 32

        def brep(uid, path):
            self.calls.append(("brep", uid, path.read_bytes()))
            if self.raise_brep:
                raise OSError("disposable BrepMFR worker failure")
            if not self.jobs[uid].get("auto_ml_enabled"):
                return None
            self.jobs[uid]["auto_ml_status"] = "queued"
            return "2" * 32

        scope = {
            "JOBS_DIR": self.data, "ROOT": self.base, "JOBS": self.jobs,
            "CURRENT": self.current, "STATE_LOCK": threading.RLock(),
            "json": __import__("json"), "sys": sys, "Path": Path,
            "set_job": set_job,
            "run_freecad_analysis": run_freecad_analysis,
            "canonicalize": lambda v: v,
            "concise_analysis": lambda v: v,
            "rule_findings": lambda v: [],
            "RECORDS": SimpleNamespace(register_cad=lambda *a: "record"),
            "archive_current_job": lambda *a: None,
            "launch_automatic_r12": r12,
            "launch_automatic_ml": brep,
        }
        exec(compile(ast.Module(body=[FN], type_ignores=[]),
                     str(SOURCE), "exec"), scope)
        self.run_job = scope["process_job"]

    def run_import(self):
        self.run_job(ID, "example.step", self.step, SHA, "freecad", "fake-FreeCAD")
        self.assertEqual(self.jobs[ID]["status"], "complete")
        self.assertFalse(self.step.exists(), "Owned disposable upload copy must be deleted")

    def test_r12_starts_even_when_brepmfr_is_available(self):
        self.run_import()
        self.assertEqual([c[0] for c in self.calls], ["r12", "brep"])
        self.assertEqual(self.jobs[ID]["auto_r12_status"], "queued")
        self.assertEqual(self.jobs[ID]["auto_ml_status"], "queued")
        self.assertEqual(self.calls[0][2], self.calls[1][2])

    def test_brepmfr_runs_when_r12_launch_fails(self):
        self.raise_r12 = True
        self.run_import()
        self.assertEqual([c[0] for c in self.calls], ["r12", "brep"])
        self.assertEqual(self.jobs[ID]["auto_ml_status"], "queued")
        self.assertEqual(self.jobs[ID]["auto_r12_status"], "failed")
        self.assertEqual(self.jobs[ID]["status"], "complete")

    def test_r12_runs_when_brepmfr_launch_fails(self):
        self.raise_brep = True
        self.run_import()
        self.assertEqual([c[0] for c in self.calls], ["r12", "brep"])
        self.assertEqual(self.jobs[ID]["auto_r12_status"], "queued")
        self.assertEqual(self.jobs[ID]["auto_ml_status"], "failed")
        self.assertEqual(self.jobs[ID]["status"], "complete")

    def test_no_unconditional_paid_api_or_fea_in_auto_process(self):
        names = {x.func.id for x in ast.walk(FN) if isinstance(x, ast.Call)
                 and isinstance(x.func, ast.Name)}
        self.assertIn("launch_automatic_r12", names)
        self.assertIn("launch_automatic_ml", names)
        for unsafe in ("execute_fea", "gf_agent_llm_optional", "start_series"):
            self.assertNotIn(unsafe, names)


if __name__ == "__main__":
    unittest.main()
