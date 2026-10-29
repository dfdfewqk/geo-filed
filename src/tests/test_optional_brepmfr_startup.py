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
                   "brepmfr_source_preflight":lambda root,digest: {
                       "state":"missing_or_unsafe_core",
                       "missing":["ml/brepmfr_worker.py",
                                  "ml/brepmfr_core/compare_preprocessing.py"],
                       "archived_worker_match":False},
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

    def test_archived_worker_missing_imports_fail_closed_and_do_not_probe_python(self):
        funcs=[node for node in TREE.body if isinstance(node,ast.FunctionDef)
               and node.name in ("brepmfr_source_preflight","ml_preflight")]
        self.assertEqual(len(funcs),2)
        consts={node.targets[0].id:ast.literal_eval(node.value)
                for node in TREE.body if isinstance(node,ast.Assign)
                and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
                and node.targets[0].id.startswith("BREPMFR_ARCHIVED_")}
        self.assertEqual(len(consts["BREPMFR_ARCHIVED_WORKER_SHA256"]),64)
        with tempfile.TemporaryDirectory(prefix="geofield-brepmfr-imports-") as tmp:
            root=Path(tmp)
            worker=root/"ml"/"brepmfr_worker.py"
            compare=root/"ml"/"brepmfr_core"/"compare_preprocessing.py"
            weights=root/"ml"/"weights"/"best-epoch43-f1_0.8626.ckpt"
            for p in (worker,compare,weights):
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(b"test-fixture")
            # The old worker has a known fingerprint, not a verified real model.
            def checksum(p):
                return (consts["BREPMFR_ARCHIVED_WORKER_SHA256"]
                        if Path(p)==worker else pinned_digest())
            def never_probe(*_):
                raise AssertionError("Missing archived worker imports should skip Python probe")
            scope={"ROOT":root,"Path":Path,"os":os,"time":__import__("time"),
                   "file_sha256":checksum,"resolve_ml_python":never_probe,
                   "REQUIRED_ML":("torch","numpy","OCP"),
                   "BREPMFR_SHA256":pinned_digest(),**consts}
            exec(compile(ast.Module(body=funcs,type_ignores=[]),str(BACKEND),"exec"),scope)
            state=scope["ml_preflight"]()
            self.assertFalse(state["available"])
            self.assertEqual(state["source_state"],"archived_worker_imports_missing")
            self.assertTrue(any("legacy_architecture.py" in m for m in state["missing"]))
            self.assertTrue(any("collator.py" in m for m in state["missing"]))
            # Completing precisely the known archived import tree is necessary
            # but not evidence of a working model or a user's installed runtime.
            for name in consts["BREPMFR_ARCHIVED_IMPORT_FILES"]:
                p=root/name
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text("pass",encoding="utf-8")
            state=scope["brepmfr_source_preflight"](root,checksum)
            self.assertEqual(state["state"],"archived_worker_imports_present")
            self.assertEqual(state["missing"],[])
            self.assertTrue(state["archived_worker_match"])

    def test_unknown_worker_is_not_asserted_to_be_archived_copy(self):
        funcs=[node for node in TREE.body if isinstance(node,ast.FunctionDef)
               and node.name=="brepmfr_source_preflight"]
        consts={node.targets[0].id:ast.literal_eval(node.value)
                for node in TREE.body if isinstance(node,ast.Assign)
                and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
                and node.targets[0].id.startswith("BREPMFR_ARCHIVED_")}
        with tempfile.TemporaryDirectory(prefix="geofield-other-worker-") as tmp:
            root=Path(tmp)
            for rel in ("ml/brepmfr_worker.py",
                        "ml/brepmfr_core/compare_preprocessing.py"):
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text("pass",encoding="utf-8")
            scope=dict(Path=Path,**consts)
            exec(compile(ast.Module(body=funcs,type_ignores=[]),str(BACKEND),"exec"),scope)
            result=scope["brepmfr_source_preflight"](root,lambda p:"0"*64)
            self.assertEqual(result["state"],"other_worker_version_not_verified")
            self.assertFalse(result["archived_worker_match"])
            self.assertFalse(result["missing"])

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
