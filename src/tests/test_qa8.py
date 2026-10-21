"""QA8: active CAD model SHA binding and direct FEA polling evidence gate.
No solver, no user files or external service is needed.
"""
import ast, copy, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'payload'/'GeoField_CAD_Analysis.py').read_text(encoding='utf8')
AST=ast.parse(SOURCE)
FUNCTION_NAMES=('qa8_verified_completed_fea_status','qa8_current_model_payload')
FUNCS=[node for node in AST.body if isinstance(node,ast.FunctionDef) and node.name in FUNCTION_NAMES]
assert len(FUNCS)==2
namespace={'Path':Path,'json':json}
exec(compile(ast.Module(body=FUNCS,type_ignores=[]),str(ROOT/'payload'/'GeoField_CAD_Analysis.py'),'exec'),namespace)
active_model=namespace['qa8_current_model_payload']
verify_status=namespace['qa8_verified_completed_fea_status']

class ModelChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'cad.json'; self.sha='a'*64
        self.path.write_text(json.dumps({'sha256':self.sha,'mesh':{'face_ids':[1,3]}}),encoding='utf8')
        self.job={'status':'complete','sha256':self.sha}
    def test_current_matching_model_returned_unchanged(self):
        self.assertEqual(active_model('j1','j1',self.job,self.path),self.path.read_bytes())
    def test_previous_cad_model_refused(self):
        with self.assertRaisesRegex(ValueError,'현재 CAD'):
            active_model('j1','j2',self.job,self.path)
    def test_pending_model_not_returned(self):
        with self.assertRaises(ValueError):active_model('j1','j1',{'status':'running','sha256':self.sha},self.path)
    def test_mismatched_step_sha_refused(self):
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            active_model('j1','j1',{'status':'complete','sha256':'b'*64},self.path)
    def test_missing_or_malformed_model_refused(self):
        self.path.unlink()
        with self.assertRaises(ValueError):active_model('j1','j1',self.job,self.path)
        self.path.write_text('[]',encoding='utf8')
        with self.assertRaises(ValueError):active_model('j1','j1',self.job,self.path)
    def test_symlink_model_refused(self):
        backing=Path(self.temp.name)/'outside.json';backing.write_bytes(self.path.read_bytes())
        self.path.unlink()
        try:self.path.symlink_to(backing)
        except (NotImplementedError,OSError):self.skipTest('symlinks not allowed on platform')
        with self.assertRaises(ValueError):active_model('j1','j1',self.job,self.path)

class FeaChecks(unittest.TestCase):
    def setUp(self):
        self.task={'id':'1'*32,'cad_job_id':'j1','status':'complete','result':{'results':{'maximum_nodal_von_mises_mpa':999}}}
        self.case={'case_sha256':'c'*64,'cad_sha256':'a'*64}
        self.called=[]
        def verifier(task,case,sha,jobs):
            self.called.append((task,case,sha,jobs))
            return {'id':task['id'],'cad_job_id':'j1','status':'complete',
                    'source_validation':'INP_STA_FRD_reverified','result':{'results':{'maximum_nodal_von_mises_mpa':3.0}}}
        namespace['reverify_task_for_display']=verifier
    def test_completed_polling_reverifies(self):
        result=verify_status(self.task,'j1','a'*64,self.case,'/tmp/a')
        self.assertEqual(result['result']['results']['maximum_nodal_von_mises_mpa'],3.0)
        self.assertEqual(self.called[0][2],'a'*64)
        self.assertEqual(self.task['result']['results']['maximum_nodal_von_mises_mpa'],999)
    def test_wrong_cad_never_calls_verifier(self):
        with self.assertRaises(ValueError):verify_status(self.task,'j2','a'*64,self.case,'/tmp/a')
        self.assertFalse(self.called)
    def test_corrupt_original_is_fail_closed(self):
        namespace['reverify_task_for_display']=Mock(return_value={
            'status':'failed','message':'계산 결과 원본 검증 실패: FRD 손상',
            'result':{'results':{'maximum_nodal_von_mises_mpa':999}}})
        result=verify_status(self.task,'j1','a'*64,self.case,'/tmp/a')
        self.assertEqual(result['status'],'failed')
        self.assertNotIn('result',result)
        self.assertIn('FRD',result['message'])
    def test_incomplete_task_cannot_pass_stale_result(self):
        task={**self.task,'status':'running'}
        namespace['reverify_task_for_display']=Mock(return_value={'status':'running','id':task['id']})
        result=verify_status(task,'j1','a'*64,self.case,'/tmp/a')
        self.assertNotIn('result',result)
    def test_missing_source_verification_cannot_pass(self):
        namespace['reverify_task_for_display']=Mock(return_value={'status':'complete','result':self.task['result']})
        out=verify_status(self.task,'j1','a'*64,self.case,'/tmp/a')
        self.assertEqual(out['status'],'failed');self.assertNotIn('result',out)

class RouteChecks(unittest.TestCase):
    def test_fea_status_uses_gate_before_return(self):
        start=SOURCE.index("if path.startswith('/api/fea/status/'):")
        end=SOURCE.index("if path.startswith('/api/ml/latest/'):",start)
        section=SOURCE[start:end]
        self.assertIn('qa8_verified_completed_fea_status(task,active',section)
        self.assertIn('return self.send_raw(checked)',section)
        self.assertNotIn('return self.send_raw(task)',section)
    def test_model_endpoint_uses_gate(self):
        start=SOURCE.index("if path.startswith('/api/model/'):")
        end=SOURCE.index("if path=='/api/fea/recovery_candidates':",start)
        section=SOURCE[start:end]
        self.assertIn('qa8_current_model_payload(uid,active',section)
        self.assertIn('return self.send_raw(payload)',section)

if __name__=='__main__':unittest.main()

class QA8UpgradeTests(unittest.TestCase):
    def test_qa7_to_qa8_single_backend_patch_idempotent_and_reversible(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('qa8_installer',ROOT/'installer.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)
            runtime=root/'GeoFieldCAD'/'onefile_runtime'/'8a9ac53a821a0eb5'
            runtime.mkdir(parents=True)
            with __import__('zipfile').ZipFile('/mnt/data/GeoField_R12_13_QA7_전체회귀_결과신뢰성_통합보관본.zip') as archive:
                for name in json.loads((ROOT/'manifest.json').read_text())['files']:
                    target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(archive.read('payload/'+name))
            (runtime/'engine_runtime.py').write_text('# Existing GeoField runtime dependency')
            protected={'jobs/L_bracket.step':b'CAD-ORIGINAL',
                       'history/geofield.sqlite3':b'SQLITE-ORIGINAL',
                       'fea_runs/real/geofield_case.frd':b'FRD-ORIGINAL',
                       'fea_runs/real/geofield_case.inp':b'INP-ORIGINAL',
                       'ml/weights/real.pt':b'ML-ORIGINAL'}
            for name,content in protected.items():
                path=runtime/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
            original=(runtime/'GeoField_CAD_Analysis.py').read_bytes()
            receipt={}
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=root,receipt=receipt),0)
            self.assertEqual([entry['path'] for entry in receipt['changed']],['GeoField_CAD_Analysis.py','frontend/cad.js'])
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=root),0)
            for name,content in protected.items():self.assertEqual((runtime/name).read_bytes(),content)
            self.assertEqual(installer.rollback_install(receipt),2)
            self.assertEqual((runtime/'GeoField_CAD_Analysis.py').read_bytes(),original)
            for name,content in protected.items():self.assertEqual((runtime/name).read_bytes(),content)
    def test_all_other_qa7_payload_files_bit_for_bit_unchanged(self):
        import zipfile
        with zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA7_전체회귀_결과신뢰성_통합보관본.zip') as archive:
            files=json.loads((ROOT/'manifest.json').read_text())['files']
            for name in files:
                if name in ('GeoField_CAD_Analysis.py','frontend/cad.js'):continue
                self.assertEqual(archive.read('payload/'+name),(ROOT/'payload'/name).read_bytes(),name)
