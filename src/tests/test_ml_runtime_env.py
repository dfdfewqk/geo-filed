"""Regression tests for active Windows ML engine selection cache."""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest import mock
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"payload/ml_env_resolver.py"
FUNCTION_NAMES={"_safe_path","_registered_marker_state","_executable_state","resolve"}

def production():
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions=[node for node in tree.body
               if isinstance(node,ast.FunctionDef) and node.name in FUNCTION_NAMES]
    assert {node.name for node in functions}==FUNCTION_NAMES
    state={"Path":Path,"os":os,"json":json,"sys":sys,"time":time,
           "threading":threading,"_CACHE":{},"_LOCK":threading.Lock(),"_TTL":75,
           "engine_python":lambda *a: {"ok":False,"path":None,"error":"unregistered"},
           "candidates":lambda *a:[Path(sys.executable)],
           "_probe":lambda path,requirements,timeout=18:{
               "ok":True,"path":str(path),"modules":{m:True for m in requirements},
               "error":""}}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(SOURCE),"exec"),state)
    return state

class CacheTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        patch=mock.patch.dict(os.environ,{"LOCALAPPDATA":str(self.root),
              "VIRTUAL_ENV":"","CONDA_PREFIX":"","GEOFIELD_R12_PYTHON":""})
        patch.start()
        self.addCleanup(patch.stop)
        self.scope=production()
        self.attempts=[]
        def probe(path,req,timeout=18):
            self.attempts.append(str(path))
            return {"ok":True,"path":str(path),"error":"",
                    "modules":{m:True for m in req}}
        self.scope["_probe"]=probe
    def resolve(self):
        return self.scope["resolve"]("GEOFIELD_R12_PYTHON",("cadquery","sklearn"))
    def test_successful_python_probe_is_cached(self):
        self.assertTrue(self.resolve()["ok"])
        self.assertTrue(self.resolve()["ok"])
        self.assertEqual(len(self.attempts),1)
    def test_active_engine_marker_change_rechecks(self):
        self.resolve()
        marker=self.root/"GeoFieldCAD"/"engines"/"engine-active-ml-r12.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"role":"ml","prefix":"changed"}))
        self.assertTrue(self.resolve()["ok"])
        self.assertEqual(len(self.attempts),2)
    def test_interpreter_replacement_invalidates_success_cache(self):
        self.resolve()
        original=self.scope["_executable_state"]
        self.scope["_executable_state"]=lambda path: ("replacement",0,0)
        self.assertTrue(self.resolve()["ok"])
        self.assertEqual(len(self.attempts),2)
        self.scope["_executable_state"]=original

    def test_virtual_environment_change_rechecks(self):
        self.resolve()
        with mock.patch.dict(os.environ,{"VIRTUAL_ENV":str(self.root/"new")}):
            self.assertTrue(self.resolve()["ok"])
        self.assertEqual(len(self.attempts),2)
    def test_negative_cache_rechecks_on_engine_marker_change(self):
        self.scope["_probe"]=lambda path,req,timeout=18:{
            "ok":False,"path":str(path),"error":"missing","modules":{}}
        self.assertFalse(self.resolve()["ok"])
        marker=self.root/"GeoFieldCAD"/"engines"/"engine-active-ml-r12.json"
        marker.parent.mkdir(parents=True)
        marker.write_text('{"role":"ml","prefix":"new"}')
        self.scope["_probe"]=lambda path,req,timeout=18:{
            "ok":True,"path":str(path),"error":"",
            "modules":{m:True for m in req}}
        self.assertTrue(self.resolve()["ok"])

if __name__=="__main__":
    unittest.main()
