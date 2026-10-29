"""GeoField: an unavailable experimental BrepMFR worker must never break CAD startup.

Uses the actual production backend source and preflight, not a fabricated model.
Does not import the private worker, execute ML, modify CAD or infer accuracy.
"""
import ast
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT/"payload"/"GeoField_CAD_Analysis.py"
AUDITOR=ROOT/"ml_runtime_source_review.py"
SRC=BACKEND.read_text(encoding="utf-8")
TREE=ast.parse(SRC)


def pinned_digest():
    items=[node for node in TREE.body if isinstance(node,ast.Assign) and
           any(isinstance(target,ast.Name) and target.id=="BREPMFR_SHA256"
               for target in node.targets)]
    if len(items)!=1 or not isinstance(items[0].value,ast.Constant):
        raise AssertionError("BrepMFR SHA-256 should be a single audited constant")
    return items[0].value.value


class OptionalBrepStartup(unittest.TestCase):
    def test_no_optional_worker_import_on_server_startup(self):
        for node in ast.walk(TREE):
            if isinstance(node,ast.ImportFrom):
                self.assertNotEqual(node.module,"ml.brepmfr_worker",
                                    "private BrepMFR worker must not be required to start CAD")
            if isinstance(node,ast.Import):
                self.assertNotIn("ml.brepmfr_worker",
                                 [x.name for x in node.names])
        self.assertIn("'ml.brepmfr_worker'",SRC,
                      "worker may still be executed by the actual ML subprocess")
        self.assertIn("import ml_r12_bridge",SRC,
                      "R12 research bridge remains in the CAD backend")

    def test_pinned_legacy_checkpoint_digest_matches_bounded_inventory(self):
        digest=pinned_digest()
        self.assertEqual(len(digest),64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))
        auditor=ast.parse(AUDITOR.read_text(encoding="utf-8"))
        matches=[node.value.value for node in auditor.body
                 if isinstance(node,ast.Assign) and
                 any(isinstance(t,ast.Name) and t.id=="CKPT_SHA256"
                     for t in node.targets) and isinstance(node.value,ast.Constant)]
        self.assertEqual(matches,[digest],
                         "the ML source review and server must verify the same epoch43 weights")

    def test_real_optional_preflight_returns_missing_model_not_import_error(self):
        target=[node for node in TREE.body
                if isinstance(node,ast.FunctionDef) and node.name=="ml_preflight"]
        self.assertEqual(len(target),1)
        with tempfile.TemporaryDirectory(prefix="geofield-optional-") as temp:
            root=Path(temp)
            def no_python_probe(*a):
                raise AssertionError("Python probe must not run if BrepMFR source is absent")
            scope={"ROOT":root,"Path":Path,"os":os,"time":__import__("time"),
                   "BREPMFR_SHA256":pinned_digest(),
                   "REQUIRED_ML":("torch","numpy"),"resolve_ml_python":no_python_probe,
                   "file_sha256":lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()}
            exec(compile(ast.Module(body=target,type_ignores=[]),
                         str(BACKEND),"exec"),scope)
            with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(root/"missing.ckpt")}):
                state=scope["ml_preflight"]()
            self.assertFalse(state["available"])
            self.assertFalse(state["checkpoint_present"])
            self.assertIn("BrepMFR worker module",state["missing"])
            self.assertIn("기존 epoch43 가중치 파일",state["missing"])
            self.assertEqual(state["python_source"],"skipped_missing_assets")

    def test_optional_ml_stays_out_of_core_status_probes(self):
        functions={x.name:x for x in TREE.body if isinstance(x,ast.FunctionDef)}
        self.assertIn("capabilities",functions)
        capability=functions["capabilities"]
        self.assertEqual(len(capability.args.defaults),1)
        self.assertEqual(ast.literal_eval(capability.args.defaults[0]),False)
        self.assertIn("probe_ml",ast.unparse(capability))
        self.assertIn("not_checked_optional",ast.unparse(capability))


if __name__=="__main__":
    unittest.main(verbosity=2)
