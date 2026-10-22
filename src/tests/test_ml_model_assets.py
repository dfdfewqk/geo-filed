"""Preflight never reuses an unverified R12 model after restart."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
BRIDGE=ROOT/"payload"/"ml_r12_bridge.py"
MODEL_ROOT=ROOT/"payload"/"ml"/"r12_research"
MODEL_HASH="df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0"

def preflight_scope():
    source=ast.parse(BRIDGE.read_text(encoding="utf-8"))
    names={"sha","locations","preflight"}
    funcs=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert {x.name for x in funcs}==names
    scope={"Path":Path,"hashlib":hashlib,"json":json,
           "EXPECTED_MODEL_SHA256":MODEL_HASH,
           "REQUIRED":("cadquery","OCP","numpy","sklearn","joblib"),
           "resolve":lambda *args:{"ok":True,"path":sys.executable,
                        "modules":{},"source":"installed","attempts":[]}}
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(BRIDGE),"exec"),scope)
    return scope

class ModelPreflightTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.base=self.root/"ml"/"r12_research"
        self.base.mkdir(parents=True)
        for file in ("research_model.joblib","report.json",
                     "worker.py","features.py","train_eval.py","build_data.py"):
            shutil.copyfile(MODEL_ROOT/file,self.base/file)
        self.ns=preflight_scope()
    def result(self):
        return self.ns["preflight"](self.root)
    def test_verified_existing_checkpoint_accepted(self):
        self.assertTrue(self.result()["available"])
    def test_changed_model_forces_unavailable(self):
        with (self.base/"research_model.joblib").open("ab") as out:
            out.write(b"changed")
        self.assertFalse(self.result()["available"])
        self.assertTrue(self.result()["missing"])
    def test_missing_model_refuses_stale_restore(self):
        (self.base/"research_model.joblib").unlink()
        self.assertFalse(self.result()["available"])
    def test_invalid_manifest_cannot_enable_model(self):
        path=self.base/"report.json"
        data=json.loads(path.read_text(encoding="utf-8"))
        data["eligible_for_production"]=True
        path.write_text(json.dumps(data),encoding="utf-8")
        self.assertFalse(self.result()["available"])
    def test_missing_worker_refuses_inference(self):
        (self.base/"worker.py").unlink()
        self.assertFalse(self.result()["available"])
    def test_installed_python_without_required_modules_is_unavailable(self):
        self.ns["resolve"]=lambda *args: {
            "ok":False,"path":None,"modules":{},"error":"missing modules"}
        self.assertFalse(self.result()["available"])

if __name__=="__main__":
    unittest.main()
