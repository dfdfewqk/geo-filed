"""REAL, trusted bundled R12 checkpoint + CadQuery STEP + independent worker smoke tests.

Requires actual cadquery/OCP/numpy/sklearn/joblib in CI. Not a mocked worker or a
user-supplied STEP. The R12 model is research-only and never FEA evidence.
All inputs/outputs are temporary; the checked-in joblib/report are read-only.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import cadquery as cq
except ImportError:
    cq = None  # A11 contract suite has no native CAD; dedicated ML CI must run this for real.

PAYLOAD = Path(__file__).resolve().parents[1] / "payload"
MODEL = PAYLOAD / "ml" / "r12_research" / "research_model.joblib"
REPORT = PAYLOAD / "ml" / "r12_research" / "report.json"
BRIDGE = PAYLOAD / "ml_r12_bridge.py"
EXPECTED = "df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validator_from_actual_bridge():
    # The private installed engine_runtime is not in public GitHub. Extract
    # only the production pure result validator; never invent a stub model.
    nodes = ast.parse(BRIDGE.read_text(encoding="utf-8")).body
    matches = [node for node in nodes if isinstance(node, ast.FunctionDef)
               and node.name == "validate_research_result"]
    if len(matches) != 1:
        raise AssertionError("Actual R12 bridge validator is missing")
    space = {"math": math}
    exec(compile(ast.Module(body=matches, type_ignores=[]), str(BRIDGE), "exec"), space)
    return space["validate_research_result"]


@unittest.skipIf(cq is None, 'CadQuery native dependency runs in dedicated real-ML workflow')
class RealR12Inference(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-r12-real-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.model_before = sha(MODEL)
        self.report_before = sha(REPORT)
        self.assertEqual(self.model_before, EXPECTED)
        manifest = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(manifest["model_sha256"], EXPECTED)
        self.assertEqual(manifest["model_use"], "research_only")
        self.assertIs(manifest["eligible_for_production"], False)

    def tearDown(self):
        self.assertEqual(sha(MODEL), self.model_before,
                         "the trusted R12 model must stay byte-identical")
        self.assertEqual(sha(REPORT), self.report_before,
                         "the evaluation report must stay byte-identical")

    def make_step(self, name, *, hole):
        solid = cq.Workplane("XY").box(50, 30, 8)
        if hole:
            solid = solid.faces(">Z").workplane().hole(5.5)
        target = self.folder / (name + ".step")
        cq.exporters.export(solid, str(target), exportType="STEP")
        self.assertGreater(target.stat().st_size, 20)
        return target

    def worker(self, step, output, *, model=MODEL, report=REPORT):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(PAYLOAD) + os.pathsep + env.get("PYTHONPATH", "")
        command = [sys.executable, "-m", "ml.r12_research.worker",
                   "--step", str(step), "--out", str(output),
                   "--model", str(model), "--manifest", str(report)]
        return subprocess.run(command, cwd=str(PAYLOAD), env=env,
                              capture_output=True, text=True, timeout=130)

    def test_real_through_bore_worker_and_production_output_validator(self):
        step = self.make_step("single-through-bore", hole=True)
        old_sha = sha(step)
        output = self.folder / "through-result.json"
        proc = self.worker(step, output)
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
        self.assertTrue(output.is_file())
        data = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data["cad_sha256"], old_sha)
        self.assertGreaterEqual(data["candidate_count"], 1,
                                "A real through-bore must yield a research candidate")
        self.assertIs(validator_from_actual_bridge()(data, old_sha), data)
        self.assertEqual(data["decision_usage"], "blocked_diagnostic_only")
        self.assertIs(data["fea_calculated"], False)
        self.assertIs(data["geometry_certified"], False)
        self.assertEqual(sha(step), old_sha, "worker must not edit input STEP")
        print("REAL R12: CadQuery STEP -> OCP bore features -> trusted joblib -> "
              f"worker output -> bridge validator; {data['candidate_count']} candidate(s)")

    def test_real_no_bore_does_not_invent_a_hole(self):
        step = self.make_step("plain-block", hole=False)
        result = self.folder / "no-bore-result.json"
        proc = self.worker(step, result)
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
        data = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(data["candidate_count"], 0)
        self.assertEqual(data["predictions"], [])
        self.assertIs(validator_from_actual_bridge()(data, sha(step)), data)

    def test_corrupt_model_copy_cannot_be_loaded_or_generate_output(self):
        step = self.make_step("rejected-model", hole=True)
        modified = self.folder / "not-trusted.joblib"
        modified.write_bytes(MODEL.read_bytes() + b"tampering")
        out = self.folder / "rejected.json"
        proc = self.worker(step, out, model=modified)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(out.exists(), "untrusted model must never produce a report")


if __name__ == "__main__":
    unittest.main(verbosity=2)
