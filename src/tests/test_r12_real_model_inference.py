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

    def test_real_r12_worker_flows_through_production_status_into_ai_evidence(self):
        # The model, STEP and subprocess are REAL. The CAD/FEA agent context
        # is explicitly synthetic; no user FRD or structural validation claim.
        import ast
        import threading
        from types import SimpleNamespace
        from test_agent_evidence import agent,record,CAD,JOB
        step=self.make_step("bridge-to-ai",hole=True)
        output=self.folder/"ai-r12-result.json"
        p=self.worker(step,output)
        self.assertEqual(p.returncode,0,p.stdout+"\\n"+p.stderr)
        data=json.loads(output.read_text(encoding="utf-8"))
        sha_value=sha(step)
        self.assertIs(validator_from_actual_bridge()(data,sha_value),data)
        source=PAYLOAD/"GeoField_CAD_Analysis.py"
        tree=ast.parse(source.read_text(encoding="utf-8"))
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef)
               and node.name=="r128_r12_status"]
        self.assertEqual(len(nodes),1)
        run_id="4"*32
        state={"STATE_LOCK":threading.RLock(),
               "R12_JOBS":{run_id:{"id":run_id,"cad_job_id":JOB,
                                   "cad_sha256":sha_value,"status":"complete",
                                   "result":data}},
               "valid_uid":lambda value:isinstance(value,str) and
                          len(value)==32 and all(ch in "0123456789abcdef" for ch in value),
               "ml_r12_bridge":SimpleNamespace(
                   validate_research_result=validator_from_actual_bridge())}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),"exec"),state)
        r12=state["r128_r12_status"](JOB,sha_value)
        self.assertEqual(r12["state"],"complete")
        self.assertEqual(r12["cad_sha256"],sha_value)
        self.assertEqual(r12["candidate_count"],data["candidate_count"])
        self.assertEqual(r12["run_id"],run_id)
        self.assertEqual(state["r128_r12_status"](JOB,"a"*64)["state"],"not_run")
        summary,decision,ml,_,fea=record()
        summary["cad"]["sha256"]=sha_value
        decision["cad_sha256"]=sha_value
        ml["cad_sha256"]=sha_value
        ml["result"]["sha256"]=sha_value
        fea["cad_sha256"]=sha_value
        fea["result"]["cad_sha256"]=sha_value
        # The original standalone agent is really executed on revalidated
        # R12 status; FEA fixture values remain synthetic evidence only.
        result=agent(summary,decision,ml,r12,fea)
        self.assertEqual(result["schema"],"geofield-evidence-agent-v1")
        self.assertEqual(result["input_contract"]["r12"]["status"],"research_complete")
        self.assertEqual(result["mode"],"rules_only")
        self.assertIs(result["fea"]["safety_certified"],False)
        self.assertFalse(result["ml"]["used_for_structural_decision"])
        self.assertTrue(all(x.get("source")!="r12_research"
                            for x in result.get("top_improvements",[])))

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
