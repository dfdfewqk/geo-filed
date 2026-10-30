"""Exercise actual GeoField receive_step handler on isolated temporary STEP uploads.

No CadQuery, live browser, private STEP, database or solver is required.
"""
import ast
import hashlib
import io
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import urllib.parse
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
handler=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=="Handler")
method=next(n for n in handler.body if isinstance(n,ast.FunctionDef) and n.name=="receive_step")


class UploadCleanupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="geofield-upload-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.uuid="a"*32
        self.thread_calls=[]
        class NoopThread:
            def __init__(inner,*args,**kwargs):
                self.thread_calls.append((args,kwargs))
            def start(inner):
                return None
        self.globals={
            "urllib":urllib,"Path":Path,"MAX_STEP":64*1024*1024,
            "detect_ocp":lambda:True,"hashlib":hashlib,
            "uuid":SimpleNamespace(uuid4=lambda:SimpleNamespace(hex=self.uuid)),
            "JOBS_DIR":self.root,"STATE_LOCK":threading.RLock(),
            "CURRENT":{},"JOBS":{},"threading":SimpleNamespace(Thread=NoopThread),
            "process_job":lambda *args:None,
        }
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(SOURCE),"exec"),
             self.globals)
        self.invoke=self.globals["receive_step"]

    def handler(self,data,declared=None):
        parent=self
        class Request:
            path="/api/cad/import?filename=single.step"
            headers={"Content-Type":"application/octet-stream",
                     "Content-Length":str(len(data) if declared is None else declared)}
            server=SimpleNamespace(freecad=None)
            rfile=io.BytesIO(data)
            def fail(self,text,code=400):
                return {"error":text,"status":code}
            def send_raw(self,result,code=200):
                self.last_response={"data":result,"status":code}
                return None  # Production handler completes via HTTP write, not return value.
        return Request()

    def test_network_disconnect_erases_owned_partial_step_without_session_change(self):
        req=self.handler(b"ISO-10303-21;unfinished",declared=500)
        with self.assertRaisesRegex(IOError,"STEP 전송"):
            self.invoke(req)
        self.assertFalse((self.root/(self.uuid+".step")).exists())
        self.assertEqual(self.globals["CURRENT"],{})
        self.assertEqual(self.globals["JOBS"],{})
        self.assertEqual(self.thread_calls,[])

    def test_uuid_collision_never_overwrites_or_deletes_someone_elses_step(self):
        existing=self.root/(self.uuid+".step")
        existing.write_bytes(b"pre-existing private STEP")
        req=self.handler(b"ISO-10303-21;valid enough bytes here")
        with self.assertRaises(FileExistsError):
            self.invoke(req)
        self.assertEqual(existing.read_bytes(),b"pre-existing private STEP")
        self.assertEqual(self.thread_calls,[])

    def test_invalid_step_header_removes_owned_copy(self):
        req=self.handler(b"THIS IS NOT A VALID STEP HEADER AT ALL")
        out=self.invoke(req)
        self.assertIn("STEP Part 21",out["error"])
        self.assertFalse((self.root/(self.uuid+".step")).exists())
        self.assertEqual(self.thread_calls,[])

    def test_complete_step_creates_one_job_and_keeps_copy_for_worker(self):
        data=b"ISO-10303-21;HEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;"
        req=self.handler(data)
        self.assertIsNone(self.invoke(req))
        out=req.last_response
        self.assertEqual(out["status"],202)
        self.assertEqual(out["data"]["id"],self.uuid)
        self.assertEqual(self.globals["CURRENT"]["pending_job_id"],self.uuid)
        self.assertEqual(self.globals["JOBS"][self.uuid]["sha256"],
                         hashlib.sha256(data).hexdigest())
        self.assertEqual((self.root/(self.uuid+".step")).read_bytes(),data)
        self.assertEqual(len(self.thread_calls),1)


if __name__=="__main__":
    unittest.main()
