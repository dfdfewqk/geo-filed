"""QA11: exact signed-case binding between approved mesh study plan and solver start.
Only mock the solver start; never label any simulated result as CalculiX evidence.
"""
import ast, hashlib, io, json, pathlib, sys, tempfile, threading, types, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'payload/GeoField_CAD_Analysis.py').read_text(encoding='utf8')
JS=(ROOT/'payload/frontend/cad.js').read_text(encoding='utf8')
AST=ast.parse(SOURCE)
handler=next(n for n in AST.body if isinstance(n,ast.ClassDef) and n.name=='Handler')
run=next(n for n in handler.body if isinstance(n,ast.FunctionDef) and n.name=='receive_mesh_series_step')
FakeHandler=type('FakeHandler',(object,),{})
# Compile only the actual production route to test it without starting HTTP server.
mod=ast.Module(body=[ast.ClassDef(name='QA11Extracted',bases=[],keywords=[],body=[run],decorator_list=[])],type_ignores=[])
ast.fix_missing_locations(mod)
ctx={'STATE_LOCK':threading.RLock(),'FEA_JOBS':{},'MESH_STUDIES':{},'ML_JOBS':{},'MAX_STEP':64*1024*1024,
     'valid_uid':lambda x:len(x)==32,'fea_solver_status':lambda:{'enabled':True,'calculix_executable':'mock-ccx'},
     'gmsh_python_status':lambda:{'ok':True},'mesh_cases':lambda c:[c,c,c],
     'hashlib':hashlib,'json':json,'uuid':__import__('uuid')}
exec(compile(mod,'qa11-actual-route','exec'),ctx)
class CaseBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.jobs_dir=pathlib.Path(self.tmp.name);self.uid='a'*32
        self.step=b'ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;'
        self.cadsha=hashlib.sha256(self.step).hexdigest()
        self.case={'cad_sha256':self.cadsha,'case_sha256':'c'*64,'mesh_request':{'target_element_size_mm':3.0}}
        (self.jobs_dir/(self.uid+'.fea_case.json')).write_text(json.dumps(self.case))
        (self.jobs_dir/(self.uid+'.json')).write_text(json.dumps({'sha256':self.cadsha}))
        ctx.update(JOBS={self.uid:{'status':'complete','sha256':self.cadsha}},CURRENT={'job_id':self.uid},JOBS_DIR=self.jobs_dir,ROOT=self.jobs_dir,HISTORY_DB='hist')
        self.calls=[]
        def fake_start(studies,lock,root,jobs_dir,hist,jobs,ml_jobs,uid,case,src,sha,ccx,gmsh):
            self.calls.append((uid,case['case_sha256'],src.read_bytes()))
            src.unlink(missing_ok=True)
            return {'id':'s'*32,'status':'queued'}
        ctx['start_series']=fake_start
        mock=types.ModuleType('r17_previous_catalog');mock.signed_case=lambda c:True
        self.modpatch=patch.dict(sys.modules,{'r17_previous_catalog':mock});self.modpatch.start();self.addCleanup(self.modpatch.stop)
    def request(self,sha,upload=True):
        inst=ctx['QA11Extracted']()
        inst.headers={'X-GeoField-Mesh-Study-Confirm':'START_THREE_REAL_SOLVES','X-GeoField-Case-SHA256':sha,
                      'Content-Length':str(len(self.step) if upload else 0),'Content-Type':'application/octet-stream'}
        inst.rfile=io.BytesIO(self.step)
        inst.fail=lambda msg,status=400:{'status':status,'error':msg}
        inst.send_raw=lambda payload,code=200:{'status':code,'payload':payload}
        return inst.receive_mesh_series_step(self.uid)
    def test_exact_approved_case_starts(self):
        r=self.request('c'*64)
        self.assertEqual(r['status'],202)
        self.assertEqual(self.calls,[(self.uid,'c'*64,self.step)])
    def test_missing_plan_signature_rejected_before_upload(self):
        r=self.request('')
        self.assertEqual(r['status'],409);self.assertIn('계획',r['error']);self.assertFalse(self.calls)
        self.assertEqual(sorted(self.jobs_dir.glob('*.mesh_study_upload.step')),[])
    def test_stale_plan_refused_even_if_cad_same(self):
        r=self.request('b'*64)
        self.assertEqual(r['status'],409);self.assertFalse(self.calls)
    def test_condition_changed_while_uploading_step_is_rejected(self):
        # A second request saves a different valid case while the HTTP body
        # is still being received. No solver worker may start on stale terms.
        original_case=self.case.copy()
        original_step=self.step
        class ChangingStep(io.BytesIO):
            def read(inner, amount=-1):
                updated=dict(original_case)
                updated['case_sha256']='f'*64
                updated['boundary_conditions']={'total_force_n':135.0}
                (self.jobs_dir/(self.uid+'.fea_case.json')).write_text(json.dumps(updated))
                return super().read(amount)
        inst=ctx['QA11Extracted']()
        inst.headers={'X-GeoField-Mesh-Study-Confirm':'START_THREE_REAL_SOLVES',
                      'X-GeoField-Case-SHA256':'c'*64,
                      'Content-Length':str(len(original_step)),
                      'Content-Type':'application/octet-stream'}
        inst.rfile=ChangingStep(original_step)
        inst.fail=lambda msg,status=400:{'status':status,'error':msg}
        inst.send_raw=lambda payload,code=200:{'status':code,'payload':payload}
        response=inst.receive_mesh_series_step(self.uid)
        self.assertEqual(response['status'],409)
        self.assertIn('업로드 중 FEA 조건',response['error'])
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.jobs_dir.glob('*.mesh_study_upload.step')),[])

    def test_same_signed_case_content_change_while_uploading_is_rejected(self):
        # Guards against partial updates or any unchanged/reused signature.
        original_step=self.step
        class ChangingStep(io.BytesIO):
            def read(inner, amount=-1):
                modified=dict(self.case)
                modified['mesh_request']={'target_element_size_mm':2.6}
                (self.jobs_dir/(self.uid+'.fea_case.json')).write_text(json.dumps(modified))
                return super().read(amount)
        inst=ctx['QA11Extracted']()
        inst.headers={'X-GeoField-Mesh-Study-Confirm':'START_THREE_REAL_SOLVES',
                      'X-GeoField-Case-SHA256':'c'*64,
                      'Content-Length':str(len(original_step)),
                      'Content-Type':'application/octet-stream'}
        inst.rfile=ChangingStep(original_step)
        inst.fail=lambda msg,status=400:{'status':status,'error':msg}
        inst.send_raw=lambda payload,code=200:{'status':code,'payload':payload}
        response=inst.receive_mesh_series_step(self.uid)
        self.assertEqual(response['status'],409)
        self.assertEqual(self.calls,[])

    def test_condition_removed_during_upload_is_rejected(self):
        original_step=self.step
        class RemovingStep(io.BytesIO):
            def read(inner, amount=-1):
                (self.jobs_dir/(self.uid+'.fea_case.json')).unlink()
                return super().read(amount)
        inst=ctx['QA11Extracted']()
        inst.headers={'X-GeoField-Mesh-Study-Confirm':'START_THREE_REAL_SOLVES',
                      'X-GeoField-Case-SHA256':'c'*64,
                      'Content-Length':str(len(original_step)),
                      'Content-Type':'application/octet-stream'}
        inst.rfile=RemovingStep(original_step)
        inst.fail=lambda msg,status=400:{'status':status,'error':msg}
        inst.send_raw=lambda payload,code=200:{'status':code,'payload':payload}
        response=inst.receive_mesh_series_step(self.uid)
        self.assertEqual(response['status'],409)
        self.assertIn('변경되거나 사라졌습니다',response['error'])
        self.assertEqual(self.calls,[])

    def test_changed_server_condition_rejected(self):
        self.case['case_sha256']='d'*64
        (self.jobs_dir/(self.uid+'.fea_case.json')).write_text(json.dumps(self.case))
        r=self.request('c'*64)
        self.assertEqual(r['status'],409);self.assertFalse(self.calls)
    def test_valid_case_still_requires_step_payload(self):
        r=self.request('c'*64,upload=False)
        self.assertEqual(r['status'],400);self.assertIn('STEP',r['error']);self.assertFalse(self.calls)
    def test_client_forwards_plan_sha_and_backend_checks_it(self):
        self.assertIn("'X-GeoField-Case-SHA256':meshSeriesPlan.base_case_sha256",JS)
        self.assertIn("expected_case_sha=self.headers.get('X-GeoField-Case-SHA256','')",SOURCE)
        self.assertIn("expected_case_sha!=case.get('case_sha256')",SOURCE)

class PreInstallChecks(unittest.TestCase):
    def test_module_list_and_preinstall_call(self):
        import bootstrap
        self.assertIn('    check_mesh_series_runtime(root)\n', (ROOT/'bootstrap.py').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            with self.assertRaisesRegex(RuntimeError,'missing'):
                bootstrap.check_mesh_series_runtime(root)
            required=('fea_mesh_series.py','fea_convergence.py','fea_compare.py','fea_previous_import.py','fea_engine_worker.py')
            for fn in required:(root/fn).write_text('')
            self.assertTrue(bootstrap.check_mesh_series_runtime(root))
            (root/'fea_mesh_series.py').unlink()
            with self.assertRaisesRegex(RuntimeError,'fea_mesh_series.py'):
                bootstrap.check_mesh_series_runtime(root)
    def test_solver_and_ml_payload_unchanged(self):
        import zipfile
        with zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA10_메시3단계_실행상태안정화_통합보관본.zip') as f:
            for name in ('fea_solver.py','fea_result_trust_gate.py','ml/r12_research/research_model.joblib','ml_r12_bridge.py'):
                self.assertEqual((ROOT/'payload'/name).read_bytes(),f.read('payload/'+name))

if __name__=='__main__':unittest.main()
