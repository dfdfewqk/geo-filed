"""R12/BrepMFR actual POST handler regression; only disposable test files.

Extracts the original Handler.receive_r12_step/receive_ml_step AST methods;
no model, network, FEA solver, actual user STEP, or checkpoint is invoked.
"""
from __future__ import annotations

import ast
import hashlib
import io
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
HANDLER=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=="Handler")
METHODS={n.name:n for n in HANDLER.body if isinstance(n,ast.FunctionDef) and
         n.name in ("receive_r12_step","receive_ml_step")}
assert len(METHODS)==2
JOB="a"*32
RID="b"*32


class MLPayloadUploadSafety(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="geofield-ml-request-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.data=b"ISO-10303-21;HEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;"
        self.sha=hashlib.sha256(self.data).hexdigest()
        self.lock=threading.RLock()
        self.jobs={JOB:{"status":"complete","sha256":self.sha}}
        self.current={"job_id":JOB}
        self.r12_jobs={}
        self.ml_jobs={}
        self.started=[]
        self.fail_thread_start=False
        outer=self
        class Thread:
            def __init__(inner,*,target,args,daemon):
                outer.started.append((target,args,daemon))
            def start(inner):
                if outer.fail_thread_start:
                    raise RuntimeError("simulated thread exhaustion")
        scope={
            "JOBS_DIR":self.root,"ROOT":self.root,
            "CURRENT":self.current,"JOBS":self.jobs,"STATE_LOCK":self.lock,
            "ML_JOBS":self.ml_jobs,"R12_JOBS":self.r12_jobs,
            "MAX_STEP":1024*1024,
            "hashlib":hashlib,"Path":Path,"os":os,
            "uuid":SimpleNamespace(uuid4=lambda:SimpleNamespace(hex=RID)),
            "threading":SimpleNamespace(Thread=Thread),
            "valid_uid":lambda x:len(x)==32 and all(c in "0123456789abcdef" for c in x),
            "ml_preflight":lambda:{"available":True,"missing":[]},
            "ml_r12_bridge":SimpleNamespace(preflight=lambda root:{"available":True,"missing":[]}),
            "execute_ml":lambda *x:None,"execute_r12":lambda *x:None,
        }
        exec(compile(ast.Module(body=list(METHODS.values()),type_ignores=[]),
                     str(SOURCE),"exec"),scope)
        self.handlers={name:scope[name] for name in METHODS}

    def request(self,payload=None,claimed=None):
        data=self.data if payload is None else payload
        class Request:
            headers={"Content-Length":str(len(data) if claimed is None else claimed),
                     "Content-Type":"application/octet-stream"}
            rfile=io.BytesIO(data)
            last_response=None
            def fail(self,message,code=400):
                return {"status":code,"error":message}
            def send_raw(self,body,code=200):
                self.last_response={"status":code,"body":body}
                return None
        return Request()

    def check_files(self,which):
        return self.root/(RID+(".r12_input.step" if which=="receive_r12_step" else ".ml_input.step"))

    def test_good_upload_queues_only_one_worker_and_preserves_owned_copy(self):
        for name in METHODS:
            with self.subTest(endpoint=name):
                self.started.clear()
                req=self.request()
                self.assertIsNone(self.handlers[name](req,JOB))
                self.assertEqual(req.last_response["status"],202)
                self.assertEqual(req.last_response["body"]["id"],RID)
                dest=self.check_files(name)
                self.assertEqual(dest.read_bytes(),self.data)
                self.assertEqual(len(self.started),1)
                state=(self.r12_jobs if name=="receive_r12_step" else self.ml_jobs)[RID]
                self.assertEqual(state["status"],"queued")
                self.assertEqual(state["cad_sha256"],self.sha)
                dest.unlink()
                self.r12_jobs.clear();self.ml_jobs.clear()

    def test_uuid_collision_must_not_overwrite_or_unlink_another_step(self):
        for name in METHODS:
            with self.subTest(endpoint=name):
                dest=self.check_files(name)
                dest.write_bytes(b"ANOTHER OWNED FILE")
                with self.assertRaises(FileExistsError):
                    self.handlers[name](self.request(),JOB)
                self.assertEqual(dest.read_bytes(),b"ANOTHER OWNED FILE")
                self.assertEqual(len(self.started),0)
                self.assertFalse(self.r12_jobs)
                self.assertFalse(self.ml_jobs)
                dest.unlink()

    def test_disconnect_deletes_only_our_partial_upload_and_enqueues_nothing(self):
        for name in METHODS:
            with self.subTest(endpoint=name):
                with self.assertRaisesRegex(IOError,"전송 중단"):
                    self.handlers[name](self.request(self.data[:30],claimed=200),JOB)
                self.assertFalse(self.check_files(name).exists())
                self.assertFalse(self.r12_jobs)
                self.assertFalse(self.ml_jobs)
                self.assertFalse(self.started)

    def test_sha_mismatch_returns_409_and_does_not_launch_model(self):
        for name in METHODS:
            with self.subTest(endpoint=name):
                body=b"ISO-10303-21;different model file;END-ISO-10303-21;"
                response=self.handlers[name](self.request(body),JOB)
                self.assertEqual(response["status"],409)
                self.assertFalse(self.check_files(name).exists())
                self.assertFalse(self.started)
                self.assertFalse(self.r12_jobs)
                self.assertFalse(self.ml_jobs)

    def test_thread_start_failure_records_failed_status_and_cleans_source(self):
        self.fail_thread_start=True
        for name in METHODS:
            with self.subTest(endpoint=name):
                result=self.handlers[name](self.request(),JOB)
                self.assertEqual(result["status"],503)
                self.assertFalse(self.check_files(name).exists())
                record=(self.r12_jobs if name=="receive_r12_step" else self.ml_jobs)[RID]
                self.assertEqual(record["status"],"failed")
                self.assertIn("스레드 시작 실패",record["message"])
                self.r12_jobs.clear();self.ml_jobs.clear()
                self.started.clear()
        self.assertEqual(self.jobs[JOB]["sha256"],self.sha)


if __name__=="__main__":
    unittest.main(verbosity=2)
