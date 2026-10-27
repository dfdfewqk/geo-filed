"""Production CAD/BrepMFR/R12 isolation functions under injected ML failures.

No actual machine-learning model, STEP file, solver, or user SQLite is loaded.
Calls to real backend worker functions are extracted from production AST.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import tempfile
import threading
import unittest
import shutil
import uuid

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SERVER.read_text(encoding="utf8"))
FUNCTIONS={"execute_ml","execute_r12","process_job","qa_validate_brepmfr_diagnostic"}
NODES=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS]
assert len(NODES)==len(FUNCTIONS)
SHA="a"*64
JOB="1"*32
RID="2"*32
FEA_RUN="3"*32
CASE_SHA="b"*64

class MLFailureIsolationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="geofield-ml-isolation-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.jobs_dir=self.root/"jobs"
        self.jobs_dir.mkdir()
        self.source_step=self.root/"owned-original.step"
        self.source_step.write_bytes(b"owner CAD is immutable")
        self.copy_step=self.jobs_dir/"temporary-ml-copy.step"
        self.copy_step.write_bytes(b"test ML input")
        self.checkpoint=self.root/"old-weights.ckpt"
        self.checkpoint.write_bytes(b"synthetic previously approved weights")
        self.archive=self.root/"history.sqlite3"
        self.archive.write_bytes(b"original user SQLite untouched")
        self.fea=self.root/"existing-result.frd"
        self.fea.write_bytes(b"existing verified solver FRD untouched")
        self.jobs={JOB:{"id":JOB,"status":"complete","sha256":SHA,
                        "auto_ml_enabled":True,"message":"CAD completed"}}
        self.fea_jobs={FEA_RUN:{"status":"complete","cad_job_id":JOB,
                               "case_sha256":CASE_SHA,"maximum_von_mises_mpa":14.5}}
        self.current={"job_id":JOB,"pending_job_id":JOB}
        self.ml_jobs={RID:{"id":RID,"cad_job_id":JOB,"cad_sha256":SHA,
                           "status":"queued"}}
        self.r12_jobs={RID:{"id":RID,"cad_job_id":JOB,"cad_sha256":SHA,
                            "status":"queued"}}
        self.trace=[]
        class Subprocess:
            CREATE_NO_WINDOW=0
            @staticmethod
            def run(*a,**kw):
                raise RuntimeError("synthetic ML worker failure")
        self.sp=Subprocess
        self.ns={
            "JOBS_DIR":self.jobs_dir,"STATE_LOCK":threading.RLock(),
            "CURRENT":self.current,"JOBS":self.jobs,"FEA_JOBS":self.fea_jobs,
            "ML_JOBS":self.ml_jobs,"R12_JOBS":self.r12_jobs,
            "ROOT":self.root,"BREPMFR_SHA256":hashlib.sha256(self.checkpoint.read_bytes()).hexdigest(),
            "REQUIRED_ML":("torch",),"resolve_ml_python":lambda *a:{"ok":True,"path":"synthetic-python"},
            "prepare_python_environment":lambda p:{},
            "os":os,"sys":SimpleNamespace(stderr=io.StringIO()),
            "subprocess":self.sp,"json":json,"math":math,
            "file_sha256":lambda p:SHA if Path(p)==self.copy_step else
                            hashlib.sha256(Path(p).read_bytes()).hexdigest(),
            "archive_current_job":lambda uid,stage:self.trace.append((uid,stage)),
            "ml_r12_bridge":SimpleNamespace(execute=lambda *a:(_ for _ in ()).throw(RuntimeError("R12 exploded"))),
        }
        exec(compile(ast.Module(body=NODES,type_ignores=[]),str(SERVER),"exec"),self.ns)
        self.original_cad=copy.deepcopy(self.jobs)
        self.original_fea=copy.deepcopy(self.fea_jobs)
        self.original_session=copy.deepcopy(self.current)

    def assert_isolated(self):
        self.assertEqual(self.jobs,self.original_cad)
        self.assertEqual(self.fea_jobs,self.original_fea)
        self.assertEqual(self.current,self.original_session)
        self.assertEqual(self.source_step.read_bytes(),b"owner CAD is immutable")
        self.assertEqual(self.archive.read_bytes(),b"original user SQLite untouched")
        self.assertEqual(self.fea.read_bytes(),b"existing verified solver FRD untouched")

    def test_worker_crash_marks_ml_only_and_deletes_only_copy(self):
        self.ns["execute_ml"](RID,JOB,self.copy_step,self.checkpoint)
        self.assertEqual(self.ml_jobs[RID]["status"],"failed")
        self.assertIn("synthetic ML worker failure",self.ml_jobs[RID]["message"])
        self.assertFalse(self.copy_step.exists())
        self.assertEqual(self.trace,[(JOB,"ml_failed")])
        self.assert_isolated()

    def test_bad_weights_marks_ml_only_without_run(self):
        self.ns["BREPMFR_SHA256"]="f"*64
        self.ns["execute_ml"](RID,JOB,self.copy_step,self.checkpoint)
        self.assertEqual(self.ml_jobs[RID]["status"],"failed")
        self.assertIn("SHA",self.ml_jobs[RID]["message"])
        self.assert_isolated()

    def test_ml_output_invalid_json_marks_ml_only(self):
        def fake_run(cmd,**kwargs):
            location=self.jobs_dir/"ml_runs"/RID/"predictions.json"
            location.write_text("{malformed",encoding="utf8")
            return SimpleNamespace(returncode=0,stdout="",stderr="")
        self.sp.run=fake_run
        self.ns["execute_ml"](RID,JOB,self.copy_step,self.checkpoint)
        self.assertEqual(self.ml_jobs[RID]["status"],"failed")
        self.assertNotIn("result",self.ml_jobs[RID])
        self.assert_isolated()

    def test_correct_ml_worker_result_is_only_research(self):
        data={"sha256":SHA,"decision_usage":"blocked_diagnostic_only",
              "variants":{"topology_trimmed":{"faces":[{"face_ordinal":1,
                 "model_score_uncalibrated":0.3,"geometry_surface":"CYLINDER",
                 "model_class":"unverified"}]}}}
        def fake_run(cmd,**kwargs):
            location=self.jobs_dir/"ml_runs"/RID/"predictions.json"
            location.write_text(json.dumps(data),encoding="utf8")
            return SimpleNamespace(returncode=0,stdout="",stderr="")
        self.sp.run=fake_run
        self.ns["execute_ml"](RID,JOB,self.copy_step,self.checkpoint)
        self.assertEqual(self.ml_jobs[RID]["status"],"complete")
        self.assertEqual(self.ml_jobs[RID]["result"],data)
        self.assertEqual(self.trace,[(JOB,"ml")])
        self.assert_isolated()

    def test_old_cad_ml_reply_is_rejected_without_changing_cad(self):
        self.current["job_id"]="4"*32
        self.original_session=copy.deepcopy(self.current)
        data={"sha256":SHA,"decision_usage":"blocked_diagnostic_only",
              "variants":{"topology_trimmed":{"faces":[]}}}
        def fake_run(cmd,**kwargs):
            (self.jobs_dir/"ml_runs"/RID/"predictions.json").write_text(json.dumps(data))
            return SimpleNamespace(returncode=0,stdout="",stderr="")
        self.sp.run=fake_run
        self.ns["execute_ml"](RID,JOB,self.copy_step,self.checkpoint)
        self.assertEqual(self.ml_jobs[RID]["status"],"failed")
        self.assertIn("현재 CAD",self.ml_jobs[RID]["message"])
        self.assert_isolated()

    def test_r12_worker_failure_leaves_all_cad_fea_files_untouched(self):
        self.ns["execute_r12"](RID,JOB,self.copy_step,SHA)
        self.assertEqual(self.r12_jobs[RID]["status"],"failed")
        self.assertFalse(self.copy_step.exists())
        self.assert_isolated()

class AutomaticLocalMLLaunchTests(unittest.TestCase):
    """The real automatic hook must enqueue once, preserve user files and need no API."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='geofield-automatic-local-ml-')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.jobs_dir=self.root/'jobs'
        self.jobs_dir.mkdir()
        self.original=self.root/'original_owned.step'
        self.original.write_bytes(b'ISO-10303-21; test CAD owner file')
        self.sha=hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.history=self.root/'owned.sqlite3'
        self.history.write_bytes(b'preserved history')
        self.solver=self.root/'owned.frd'
        self.solver.write_bytes(b'preserved solver output')
        self.jobs={JOB:{'id':JOB,'sha256':self.sha,'status':'complete','auto_ml_enabled':True}}
        self.ml_jobs={}
        self.session={'job_id':JOB}
        self.enqueued=[]
        class FakeThread:
            def __init__(inner,target,args,daemon=False):
                self.enqueued.append((target,args,daemon))
            def start(inner):
                pass
        scope={
            'JOBS_DIR':self.jobs_dir,'ROOT':self.root,
            'STATE_LOCK':threading.RLock(),'CURRENT':self.session,
            'JOBS':self.jobs,'ML_JOBS':self.ml_jobs,
            'ml_preflight':lambda:{'available':True,'missing':[]},
            'file_sha256':lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'uuid':uuid,'os':os,'Path':Path,'shutil':shutil,
            'threading':SimpleNamespace(Thread=FakeThread),
            'execute_ml':lambda *a:None,
        }
        selected=[n for n in TREE.body
                  if isinstance(n,ast.FunctionDef) and n.name=='launch_automatic_ml']
        self.assertEqual(len(selected),1)
        exec(compile(ast.Module(body=selected,type_ignores=[]),str(SERVER),'exec'),scope)
        self.scope=scope
        self.launch=scope['launch_automatic_ml']

    def check_preserved(self):
        self.assertEqual(self.original.read_bytes(),b'ISO-10303-21; test CAD owner file')
        self.assertEqual(self.history.read_bytes(),b'preserved history')
        self.assertEqual(self.solver.read_bytes(),b'preserved solver output')

    def test_local_auto_ml_enqueues_once_with_copy_and_verified_sha(self):
        rid=self.launch(JOB,self.original)
        self.assertTrue(isinstance(rid,str) and len(rid)==32 and all(c in '0123456789abcdef' for c in rid))
        self.assertEqual(len(self.enqueued),1)
        copied=self.jobs_dir/(rid+'.ml_input.step')
        self.assertEqual(copied.read_bytes(),self.original.read_bytes())
        self.assertEqual(self.ml_jobs[rid]['cad_sha256'],self.sha)
        self.assertEqual(self.ml_jobs[rid]['status'],'queued')
        self.assertTrue(self.ml_jobs[rid]['automatic'])
        self.assertEqual(self.jobs[JOB]['auto_ml_run_id'],rid)
        self.assertEqual(self.launch(JOB,self.original),rid)
        self.assertEqual(len(self.enqueued),1)
        self.check_preserved()

    def test_saved_opt_out_never_starts_worker(self):
        self.jobs[JOB]['auto_ml_enabled']=False
        self.assertIsNone(self.launch(JOB,self.original))
        self.assertEqual(self.jobs[JOB]['auto_ml_status'],'disabled_by_user')
        self.assertFalse(self.enqueued)
        self.assertFalse(self.ml_jobs)
        self.check_preserved()

    def test_missing_existing_model_does_not_create_fake_success(self):
        self.scope['ml_preflight']=lambda:{'available':False,'missing':['BrepMFR worker module']}
        self.assertIsNone(self.launch(JOB,self.original))
        self.assertEqual(self.jobs[JOB]['auto_ml_status'],'unavailable')
        self.assertIn('BrepMFR worker module',self.jobs[JOB]['auto_ml_message'])
        self.assertFalse(self.enqueued)
        self.assertFalse(self.ml_jobs)
        self.check_preserved()

    def test_wrong_step_sha_never_enqueues_anything(self):
        self.jobs[JOB]['sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'해시 검증'):
            self.launch(JOB,self.original)
        self.assertFalse(self.enqueued)
        self.assertFalse(self.ml_jobs)
        self.check_preserved()

    def test_other_active_cad_cannot_trigger_old_ml(self):
        self.session['job_id']='7'*32
        self.assertIsNone(self.launch(JOB,self.original))
        self.assertFalse(self.enqueued)
        self.assertFalse(self.ml_jobs)
        self.check_preserved()


if __name__=="__main__":
    unittest.main()
