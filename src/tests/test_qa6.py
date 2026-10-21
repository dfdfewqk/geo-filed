"""QA6: read-only, synthetic mesh-study integrity regression (NO CalculiX executions)."""
import ast, copy, hashlib, json, re, sqlite3, types, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'payload/GeoField_CAD_Analysis.py'

class Q6MeshBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
        fn=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='r1213_mesh_series_verified_public']
        assert len(fn)==1
        code=compile(ast.Module(body=fn,type_ignores=[]),str(SOURCE),'exec')
        def public_state(study):
            return {k:copy.deepcopy(v) for k,v in study.items() if k in ('id','cad_sha256','sizes_mm','status','analysis_snapshot_ids','mesh_study_verified','study_analysis')}
        env={'public_state':public_state,'sqlite3':sqlite3}
        exec(code,env)
        cls.fn=staticmethod(env['r1213_mesh_series_verified_public'])
        cls.env=env
    def data(self):
        sha='a'*64
        sizes=[4.2,3.0,2.25]
        ids=['1'*32,'2'*32,'3'*32]
        study={'id':'0'*32,'cad_sha256':sha,'sizes_mm':sizes,'status':'complete','analysis_snapshot_ids':ids,'mesh_study_verified':True}
        runs=[{'cad_sha256':sha,'snapshot_id':sid,'mesh_target_mm':size} for sid,size in zip(ids,sizes)]
        analysis={'status':'verified_three_mesh_sensitivity_only','runs_coarse_to_fine':runs,'numeric_stability_diagnostic':{'passes':True}}
        return study,analysis
    def run_checked(self,study,analysis):
        self.env['r1213_verified_mesh_spatial_study']=lambda _ids:analysis
        return self.fn(study)
    def test_approved_three_mesh_study(self):
        study,analysis=self.data(); result=self.run_checked(study,analysis)
        self.assertTrue(result['mesh_study_verified']);self.assertEqual(result['study_analysis'],analysis)
    def test_mismatched_cad_rejected(self):
        study,analysis=self.data();study['cad_sha256']='b'*64
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified']);self.assertIn('불일치',result['verification_warning'])
    def test_wrong_study_run_id_rejected(self):
        study,analysis=self.data();analysis['runs_coarse_to_fine'][2]['snapshot_id']='f'*32
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified'])
    def test_mismatched_mesh_size_rejected(self):
        study,analysis=self.data();analysis['runs_coarse_to_fine'][1]['mesh_target_mm']=3.1
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified'])
    def test_duplicate_snapshot_ids_rejected(self):
        study,analysis=self.data();study['analysis_snapshot_ids'][2]=study['analysis_snapshot_ids'][1]
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified'])
    def test_incomplete_three_mesh_study(self):
        study,analysis=self.data();study['analysis_snapshot_ids'].pop()
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified'])
    def test_stale_cancelled_claim_rejected(self):
        study,analysis=self.data();study['status']='cancelled'
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified']);self.assertIsNone(result['study_analysis'])
    def test_missing_original_sha_rejected(self):
        study,analysis=self.data();study['cad_sha256']=None
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified'])
    def test_original_not_mutated_on_failure(self):
        study,analysis=self.data();study['sizes_mm'][0]=9.
        snap=copy.deepcopy(study)
        result=self.run_checked(study,analysis)
        self.assertFalse(result['mesh_study_verified']);self.assertEqual(study,snap)
    def test_frontend_invalid_percent_not_rendered_as_zero(self):
        src=(ROOT/'payload/frontend/cad.js').read_text(encoding='utf-8')
        self.assertIn("typeof v==='number'&&Number.isFinite(v)&&v>=0",src)
        self.assertNotIn('Number(x.stress_relative_change_percent).toFixed(3)',src)
        self.assertNotIn('Number(x.displacement_relative_change_percent).toFixed(3)',src)

if __name__=='__main__':unittest.main(verbosity=2)

class Q6InstallerRegression(unittest.TestCase):
    def test_qa5_to_qa6_update_idempotency_and_rollback(self):
        import importlib.util, tempfile, zipfile
        spec=importlib.util.spec_from_file_location('qa6_installer',ROOT/'installer.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as d:
            temp=Path(d)
            runtime=temp/'GeoFieldCAD'/'onefile_runtime'/'8a9ac53a821a0eb5'
            runtime.mkdir(parents=True)
            old=Path('/mnt/data/GeoField_R12_13_QA5_메시수렴_보고서일치_통합보관본.zip')
            if not old.is_file():self.skipTest('QA5 archive not mounted')
            with zipfile.ZipFile(old) as z:
                for name in json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))['files']:
                    path=runtime/name;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(z.read('payload/'+name) if name != 'fea_result_trust_gate.py' else Path('/mnt/data/geofield_qa6_work/fea_result_trust_gate.py').read_bytes())
            (runtime/'engine_runtime.py').write_text('# runtime remains untouched\n')
            files={'L_bracket.step':b'USER STEP data immutable',
                   'history.sqlite':b'USER SQLITE data immutable',
                   'fea_runs/id/geofield_case.frd':b'USER FRD data immutable',
                   'ml/custom_weights.pt':b'USER ML weights immutable'}
            for name,data in files.items():
                path=runtime/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            backend=runtime/'GeoField_CAD_Analysis.py';js=runtime/'frontend/cad.js'
            previous=(backend.read_bytes(),js.read_bytes())
            receipt={}
            changed=m.apply(m.DirectoryBundle(ROOT),localappdata=temp,receipt=receipt)
            self.assertEqual(len(receipt['changed']),3)
            self.assertEqual(backend.read_bytes(),(ROOT/'payload/GeoField_CAD_Analysis.py').read_bytes())
            self.assertEqual(js.read_bytes(),(ROOT/'payload/frontend/cad.js').read_bytes())
            self.assertEqual(m.apply(m.DirectoryBundle(ROOT),localappdata=temp),0)
            for name,data in files.items():self.assertEqual((runtime/name).read_bytes(),data)
            self.assertEqual(m.rollback_install(receipt),3)
            self.assertEqual((backend.read_bytes(),js.read_bytes()),previous)
            for name,data in files.items():self.assertEqual((runtime/name).read_bytes(),data)
