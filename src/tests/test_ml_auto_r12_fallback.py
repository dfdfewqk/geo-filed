"""GeoField ML fallback contract: AST-isolated real production functions.

No fake CAD geometry or ML model output is counted as real inference.
The test mocks only subprocess/thread boundaries while exercising production
SHA/copy/current-STEP guards. Actual STEP inference is a separate test.
"""
import ast
import hashlib
import json
import os
import shutil
import tempfile
import threading
import types
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = Path(os.getenv('GEOFIELD_TEST_SERVER_FILE', ROOT / 'payload/GeoField_CAD_Analysis.py'))


def load_contract(*names):
    tree=ast.parse(SERVER.read_text(encoding='utf-8'))
    found=[node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    if len(found)!=len(names):
        raise AssertionError(f'missing functions: {set(names)-{node.name for node in found}}')
    code=compile(ast.Module(body=found,type_ignores=[]),str(SERVER),'exec')
    scope={'file_sha256': lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
           'shutil':shutil,'uuid':uuid,'threading':threading,'Path':Path}
    exec(code,scope)
    return scope


class DeferredThread:
    threads=[]
    def __init__(self,target,args,daemon):
        assert daemon is True
        self.fn,self.args=target,args
    def start(self):
        self.threads.append(self)


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.step=self.root/'cad.step';self.step.write_bytes(b'ISO-10303-21;\nREAL STEP bytes sample\n')
        self.sha=hashlib.sha256(self.step.read_bytes()).hexdigest()
        self.cad_id=uuid.uuid4().hex
        self.job={'sha256':self.sha,'status':'complete'}
        self.ns=load_contract('launch_automatic_r12','execute_r12')
        self.ns.update({'ROOT':self.root,'JOBS_DIR':self.root,'STATE_LOCK':threading.RLock(),
                        'CURRENT':{'job_id':self.cad_id},'JOBS':{self.cad_id:self.job},
                        'R12_JOBS':{},'ml_r12_bridge':types.SimpleNamespace(
                            preflight=lambda _: {'available':True,'missing':[]},
                            execute=lambda *args: {'cad_sha256':self.sha,'status':'research_not_for_production',
                                                       'decision_usage':'blocked_diagnostic_only',
                                                       'candidate_count':0,'predictions':[]}),
                        'threading':types.SimpleNamespace(Thread=DeferredThread)})
        DeferredThread.threads=[]

    def start(self):
        return self.ns['launch_automatic_r12'](self.cad_id,self.step,self.job,{'missing':['BrepMFR checkpoint absent']})

    def test_success_shamatch_and_research_status(self):
        rid=self.start()
        state=self.ns['R12_JOBS'][rid]
        self.assertEqual((state['provider'],state['status'],state['automatic']),('r12','queued',True))
        self.assertTrue(self.step.exists())
        self.assertEqual(len(DeferredThread.threads),1)
        DeferredThread.threads.pop().fn(* (rid,self.cad_id,self.root/(rid+'.r12_input.step'),self.sha))
        self.assertEqual(self.ns['R12_JOBS'][rid]['status'],'complete')
        self.assertEqual(self.job['auto_ml_status'],'complete')
        self.assertFalse((self.root/(rid+'.r12_input.step')).exists())
        self.assertTrue(self.step.exists())

    def test_second_request_does_not_duplicate(self):
        rid=self.start();self.assertEqual(rid,self.start())
        self.assertEqual(len(DeferredThread.threads),1)

    def test_both_models_unavailable_reports_reason(self):
        self.ns['ml_r12_bridge'].preflight=lambda _: {'available':False,'missing':['scikit-learn missing']}
        self.assertIsNone(self.start())
        self.assertEqual(self.job['auto_ml_status'],'unavailable')
        self.assertIn('BrepMFR checkpoint absent',self.job['auto_ml_message'])
        self.assertIn('scikit-learn missing',self.job['auto_ml_message'])
        self.assertFalse(DeferredThread.threads)

    def test_tampered_step_refused_before_copy(self):
        self.step.write_bytes(b'change CAD before model input')
        with self.assertRaisesRegex(ValueError,'SHA'):
            self.start()
        self.assertFalse(DeferredThread.threads)

    def test_switching_cad_discards_old_result(self):
        rid=self.start()
        self.ns['CURRENT']['job_id']=uuid.uuid4().hex
        DeferredThread.threads.pop().fn(rid,self.cad_id,self.root/(rid+'.r12_input.step'),self.sha)
        self.assertEqual(self.ns['R12_JOBS'][rid]['status'],'failed')
        self.assertEqual(self.job['auto_ml_status'],'failed')
        self.assertNotIn('result',self.ns['R12_JOBS'][rid])
        self.assertTrue(self.step.exists())

    def test_failed_model_does_not_modify_cad(self):
        rid=self.start()
        def fail(*args): raise RuntimeError('real inference unavailable')
        self.ns['ml_r12_bridge'].execute=fail
        DeferredThread.threads.pop().fn(rid,self.cad_id,self.root/(rid+'.r12_input.step'),self.sha)
        self.assertEqual(self.ns['R12_JOBS'][rid]['status'],'failed')
        self.assertEqual(self.job['auto_ml_status'],'failed')
        self.assertEqual(hashlib.sha256(self.step.read_bytes()).hexdigest(),self.sha)

    def test_frontend_wires_fallback_and_separate_stale_results(self):
        ui=(SERVER.parent/'frontend/cad.js').read_text(encoding='utf-8')
        assert "if(task.provider==='r12')" in ui
        assert "r?.cad_sha256!==expectedSha" in ui
        assert "stepSelectionVersion===selection" in ui
        assert "localStorage.getItem('geofield_auto_ml_enabled')!=='false'" in ui


if __name__=='__main__': unittest.main()
