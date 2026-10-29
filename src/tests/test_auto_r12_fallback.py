"""Execute production automatic R12 fallback on isolated STEP bytes.

No installed BrepMFR worker, model execution, FEA computation, network, or
user-owned files are invoked. This explicitly exercises per-import consent,
CAD/SHA identity, dedupe, collision and failure cleanup.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest

SERVER=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SERVER.read_text(encoding="utf8"))
FUNCS={x.name:x for x in TREE.body if isinstance(x,ast.FunctionDef)
       and x.name in ("launch_automatic_ml","launch_automatic_r12")}
assert len(FUNCS)==2
JOB="a"*32
RID="b"*32


class AutoR12Fallback(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="geofield-r12-fallback-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.folder=self.root/"jobs";self.folder.mkdir()
        self.original=self.root/"owner-original.step"
        self.original.write_bytes(b"ISO-10303-21; owner original CAD")
        self.sha=hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.history=self.root/"user-owned.sqlite3"
        self.history.write_bytes(b"private history untouched")
        self.fea=self.root/"owned.frd"
        self.fea.write_bytes(b"verified FRD untouched")
        self.jobs={JOB:{"status":"complete","sha256":self.sha,
                        "auto_ml_enabled":True}}
        self.current={"job_id":JOB}
        self.ml_jobs={};self.r12_jobs={}
        self.ready={"available":True,"missing":[]}
        self.calls=[];self.thread_failure=False
        outer=self
        class WorkerThread:
            def __init__(inner,*,target,args,daemon):
                outer.calls.append((target,args,daemon))
            def start(inner):
                if outer.thread_failure:
                    raise RuntimeError("artificial test cannot start thread")
        self.scope={
            "ROOT":self.root,"JOBS_DIR":self.folder,
            "STATE_LOCK":threading.RLock(),"CURRENT":self.current,
            "JOBS":self.jobs,"ML_JOBS":self.ml_jobs,
            "R12_JOBS":self.r12_jobs,
            "ml_preflight":lambda:{"available":False,
                                   "missing":["BrepMFR worker module"]},
            "ml_r12_bridge":SimpleNamespace(preflight=lambda root:self.ready),
            "file_sha256":lambda file:hashlib.sha256(Path(file).read_bytes()).hexdigest(),
            "Path":Path,"shutil":shutil,"os":os,
            "uuid":SimpleNamespace(uuid4=lambda:SimpleNamespace(hex=RID)),
            "threading":SimpleNamespace(Thread=WorkerThread),
            "execute_r12":lambda *x:None,
        }
        exec(compile(ast.Module(body=list(FUNCS.values()),type_ignores=[]),
                     str(SERVER),"exec"),self.scope)
        self.start=self.scope["launch_automatic_ml"]

    def unchanged(self):
        self.assertEqual(self.original.read_bytes(),b"ISO-10303-21; owner original CAD")
        self.assertEqual(self.history.read_bytes(),b"private history untouched")
        self.assertEqual(self.fea.read_bytes(),b"verified FRD untouched")

    def test_unavailable_brepmfr_triggers_real_source_r12_queue_only_when_opted_in(self):
        self.assertEqual(self.start(JOB,self.original),RID)
        self.assertEqual(self.jobs[JOB]["auto_ml_status"],"r12_fallback")
        self.assertEqual(self.jobs[JOB]["auto_r12_status"],"queued")
        self.assertEqual(self.jobs[JOB]["auto_r12_run_id"],RID)
        self.assertEqual(self.r12_jobs[RID]["cad_sha256"],self.sha)
        self.assertTrue(self.r12_jobs[RID]["automatic"])
        self.assertEqual(self.r12_jobs[RID]["status"],"queued")
        copied=self.folder/(RID+".r12_input.step")
        self.assertEqual(copied.read_bytes(),self.original.read_bytes())
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.start(JOB,self.original),RID)
        self.assertEqual(len(self.calls),1,"must not start duplicate R12 worker")
        self.unchanged()

    def test_opt_out_never_attempts_any_ml(self):
        self.jobs[JOB]["auto_ml_enabled"]=False
        self.assertIsNone(self.start(JOB,self.original))
        self.assertEqual(self.jobs[JOB]["auto_ml_status"],"disabled_by_user")
        self.assertFalse(self.calls)
        self.assertFalse(self.r12_jobs)
        self.unchanged()

    def test_no_r12_model_still_preserves_cad_and_reports_not_ready(self):
        self.ready={"available":False,"missing":["research_model.joblib absent"]}
        self.assertIsNone(self.start(JOB,self.original))
        self.assertEqual(self.jobs[JOB]["auto_ml_status"],"r12_fallback")
        self.assertEqual(self.jobs[JOB]["auto_r12_status"],"unavailable")
        self.assertIn("research_model.joblib",self.jobs[JOB]["auto_r12_message"])
        self.assertFalse(self.calls)
        self.assertFalse(self.r12_jobs)
        self.unchanged()

    def test_wrong_step_or_switched_cad_never_creates_result(self):
        self.jobs[JOB]["sha256"]="c"*64
        with self.assertRaisesRegex(ValueError,"해시"):
            self.start(JOB,self.original)
        self.assertFalse(self.r12_jobs)
        self.unchanged()
        self.jobs[JOB]["sha256"]=self.sha
        self.current["job_id"]="e"*32
        self.assertIsNone(self.start(JOB,self.original))
        self.assertFalse(self.r12_jobs)
        self.assertEqual(self.calls,[])
        self.unchanged()

    def test_existing_r12_copy_never_overwritten_or_deleted(self):
        target=self.folder/(RID+".r12_input.step")
        target.write_bytes(b"OTHER private file")
        with self.assertRaises(FileExistsError):
            self.start(JOB,self.original)
        self.assertEqual(target.read_bytes(),b"OTHER private file")
        self.assertFalse(self.calls)
        self.assertFalse(self.r12_jobs)
        self.unchanged()

    def test_thread_start_failed_marks_failed_and_cleans_owned_copy(self):
        self.thread_failure=True
        with self.assertRaisesRegex(RuntimeError,"cannot start"):
            self.start(JOB,self.original)
        self.assertFalse((self.folder/(RID+".r12_input.step")).exists())
        self.assertEqual(self.r12_jobs[RID]["status"],"failed")
        self.assertEqual(self.jobs[JOB]["auto_r12_status"],"failed")
        self.unchanged()


if __name__=="__main__":
    unittest.main(verbosity=2)
