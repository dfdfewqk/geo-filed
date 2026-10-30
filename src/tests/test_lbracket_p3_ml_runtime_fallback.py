"""P3 L-bracket: actual existing BrepMFR runtime failure gets an honest R12 fallback.

No native model, user's actual STEP, FEA, LLM, private checkpoint or Windows
application is invoked. Synthetic bytes and an injected crashing ML process
test the production functions' control-flow and immutable-file boundaries.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest

SERVER=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SERVER.read_text(encoding="utf8"))
NAMES={"execute_ml","qa_public_automatic_ml_fallback","qa_validate_brepmfr_diagnostic"}
NODES=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
assert len(NODES)==len(NAMES)
CAD_ID="1"*32
ML_ID="2"*32
CAD_SHA=hashlib.sha256(b"SYNTHETIC TEST L BRACKET").hexdigest()


class AutoFailedWorkerToR12(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="geofield-lbracket-p3-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.jobs=self.root/"jobs"
        self.jobs.mkdir()
        self.original=self.root/"owner-original.step"
        self.original.write_bytes(b"SYNTHETIC TEST L BRACKET")
        self.ml_copy=self.jobs/"only-ml-working-copy.step"
        self.ml_copy.write_bytes(self.original.read_bytes())
        self.ckpt=self.root/"fake-weight.ckpt"
        self.ckpt.write_bytes(b"FAKE MODEL CHECKPOINT NOT REAL")
        self.private_files=[self.original,self.ckpt]
        self.private_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in self.private_files}
        self.sqlite=self.root/"real-history-placeholder.sqlite"
        self.sqlite.write_bytes(b"ORIGINAL ARCHIVED USER HISTORY IS NEVER OPENED")
        self.frd=self.root/"prior-frd-placeholder.frd"
        self.frd.write_bytes(b"REAL USER FEA IS NEVER OPENED")
        self.private_files.extend([self.sqlite,self.frd])
        self.private_hashes.update({
            str(p):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (self.sqlite,self.frd)})
        self.current={"job_id":CAD_ID}
        self.cad={CAD_ID:{"id":CAD_ID,"sha256":CAD_SHA,"status":"complete",
                          "auto_ml_enabled":True,
                          "auto_ml_run_id":ML_ID,"auto_ml_status":"queued"}}
        self.ml={ML_ID:{"id":ML_ID,"cad_job_id":CAD_ID,"cad_sha256":CAD_SHA,
                        "automatic":True,"status":"queued"}}
        self.fea={"4"*32:{"status":"complete","value":18.86}}
        self.before_fea=copy.deepcopy(self.fea)
        self.before_original_cad={k:{"id":v["id"],"sha256":v["sha256"],
                                      "status":v["status"]} for k,v in self.cad.items()}
        self.fallback=[];self.archived=[]
        outer=self
        class CrashingML:
            @staticmethod
            def run(*args,**kwargs):
                if outer.on_crash:
                    outer.on_crash()
                raise RuntimeError("synthetic installed BrepMFR worker failed")
        self.on_crash=None
        def fake_r12(job_id,source):
            outer.fallback.append((job_id,Path(source),outer.ml_copy.exists()))
            if outer.r12_crashes:
                raise RuntimeError("R12 unavailable")
            if not outer.r12_ready:
                outer.cad[job_id]["auto_r12_status"]="unavailable"
                return None
            outer.cad[job_id]["auto_r12_status"]="queued"
            return "3"*32
        self.r12_crashes=False;self.r12_ready=True
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        ns={"ROOT":self.root,"JOBS_DIR":self.jobs,"STATE_LOCK":threading.RLock(),
            "JOBS":self.cad,"ML_JOBS":self.ml,"FEA_JOBS":self.fea,
            "CURRENT":self.current,
            "BREPMFR_SHA256":sha(self.ckpt),
            "REQUIRED_ML":("torch",),
            "resolve_ml_python":lambda *args:{"ok":True,"path":"synthetic-python"},
            "prepare_python_environment":lambda p:{},
            "file_sha256":sha,"Path":Path,"os":os,"json":json,
            "sys":SimpleNamespace(stderr=io.StringIO()),
            "subprocess":CrashingML,
            "archive_current_job":lambda uid,stage:outer.archived.append((uid,stage)),
            "launch_automatic_r12":fake_r12}
        exec(compile(ast.Module(body=NODES,type_ignores=[]),str(SERVER),"exec"),ns)
        self.execute=ns["execute_ml"]
        self.public=ns["qa_public_automatic_ml_fallback"]

    def assert_immutable(self):
        for p in self.private_files:
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),
                             self.private_hashes[str(p)])
        self.assertEqual(self.fea,self.before_fea)
        for k,original in self.before_original_cad.items():
            for name,value in original.items():
                self.assertEqual(self.cad[k][name],value)

    def test_real_worker_exception_starts_existing_r12_only_for_auto_same_step(self):
        self.execute(ML_ID,CAD_ID,self.ml_copy,self.ckpt)
        self.assertEqual(self.ml[ML_ID]["status"],"failed")
        self.assertIn("synthetic installed BrepMFR worker failed",
                      self.ml[ML_ID]["message"])
        self.assertEqual(self.fallback,[(CAD_ID,self.ml_copy,True)])
        self.assertEqual(self.cad[CAD_ID]["auto_ml_status"],"r12_fallback")
        self.assertEqual(self.cad[CAD_ID]["auto_r12_status"],"queued")
        self.assertFalse(self.ml_copy.exists())
        self.assertNotIn("result",self.ml[ML_ID])
        self.assertEqual(self.archived,[(CAD_ID,"ml_failed")])
        public=self.public(self.ml[ML_ID],self.cad[CAD_ID])
        self.assertEqual(public["status"],"r12_fallback")
        self.assertIn("BrepMFR 실행 실패",public["message"])
        self.assertEqual(self.ml[ML_ID]["status"],"failed",
                         "Recorded real BrepMFR worker failure must stay failed")
        self.assert_immutable()

    def test_manual_failure_must_not_trigger_r12(self):
        self.ml[ML_ID]["automatic"]=False
        self.execute(ML_ID,CAD_ID,self.ml_copy,self.ckpt)
        self.assertFalse(self.fallback)
        self.assertEqual(self.ml[ML_ID]["status"],"failed")
        self.assertEqual(self.cad[CAD_ID]["auto_ml_status"],"queued")
        self.assertEqual(self.public(self.ml[ML_ID],self.cad[CAD_ID])["status"],"failed")
        self.assert_immutable()

    def test_opt_out_and_changed_active_cad_block_fallback(self):
        for mode in ("optout","newcad"):
            with self.subTest(mode=mode):
                self.setUp()
                def change():
                    if mode=="optout":self.cad[CAD_ID]["auto_ml_enabled"]=False
                    else:self.current["job_id"]="f"*32
                self.on_crash=change
                self.execute(ML_ID,CAD_ID,self.ml_copy,self.ckpt)
                self.assertFalse(self.fallback)
                self.assertEqual(self.ml[ML_ID]["status"],"failed")
                self.assertFalse(self.ml_copy.exists())
                self.assert_immutable()

    def test_replaced_input_sha_blocks_research_copy(self):
        self.on_crash=lambda:self.ml_copy.write_bytes(b"TAMPERED STEP")
        self.execute(ML_ID,CAD_ID,self.ml_copy,self.ckpt)
        self.assertFalse(self.fallback)
        self.assertEqual(self.cad[CAD_ID]["auto_ml_status"],"failed")
        self.assertNotIn("result",self.ml[ML_ID])
        self.assertFalse(self.ml_copy.exists())
        self.assert_immutable()

    def test_r12_missing_reports_unavailable_without_masking_original_ml_fail(self):
        self.r12_ready=False
        self.execute(ML_ID,CAD_ID,self.ml_copy,self.ckpt)
        self.assertEqual(self.cad[CAD_ID]["auto_r12_status"],"unavailable")
        self.assertEqual(self.cad[CAD_ID]["auto_ml_status"],"r12_fallback")
        self.assertEqual(self.ml[ML_ID]["status"],"failed")
        self.assert_immutable()

    def test_fallback_launcher_error_reports_both_failures_and_no_more_retries(self):
        self.r12_crashes=True
        self.execute(ML_ID,CAD_ID,self.ml_copy,self.ckpt)
        self.assertEqual(self.cad[CAD_ID]["auto_ml_status"],"failed")
        self.assertIn("R12 unavailable",self.cad[CAD_ID]["auto_ml_message"])
        self.assertEqual(self.ml[ML_ID]["status"],"failed")
        self.assertEqual(self.public(self.ml[ML_ID],self.cad[CAD_ID])["status"],"failed")
        self.assert_immutable()

    def test_fallback_helper_rejects_manual_and_unrelated_run(self):
        self.ml[ML_ID]["status"]="failed"
        self.cad[CAD_ID]["auto_ml_status"]="r12_fallback"
        for change in (
            {"automatic":False},{"id":"5"*32},
            {"cad_sha256":"d"*64},{"status":"complete"}):
            with self.subTest(change=change):
                candidate=dict(self.ml[ML_ID],**change)
                self.assertEqual(self.public(candidate,self.cad[CAD_ID])["status"],
                                 candidate["status"])


if __name__=="__main__":
    unittest.main()
