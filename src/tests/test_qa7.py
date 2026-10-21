"""QA7 real-archive-backed report consistency plus ML/mesh/installer contracts.
Uses archived actual 3kg CalculiX output; NO new solver calculation and NO user files modified.
"""
import copy, hashlib, importlib.util, json, tempfile, unittest, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ORIG = Path('/mnt/data/geofield_qa6_work')
EVIDENCE = Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')
spec = importlib.util.spec_from_file_location('qa7_trust', ROOT / 'fea_result_trust_gate.py')
trust = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trust)

class QA7TrustGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(EVIDENCE) as z:
            cls.result=json.loads(z.read('09ef27cabe074bfa84b413d786fe075e/result.json'))
        cls.run_id='09ef27cabe074bfa84b413d786fe075e'
    def sample(self):
        r=self.result
        entry={'cad':{'sha256':r['cad_sha256']},'fea':{
            'state':'complete','result_run_id':self.run_id,'result_case_sha256':r['case_sha256'],
            'maximum_von_mises_mpa':r['results']['maximum_nodal_von_mises_mpa'],
            'maximum_displacement_mm':r['results']['maximum_displacement_mm'],
            'node_count':r['mesh']['node_count'],
            'tetrahedron_count':r['mesh']['tetrahedron_count'],
            'field_visualization':{'available':True}}}
        actual={'snapshot_id':'f'*32,'cad_sha256':r['cad_sha256'],
            'run_id':self.run_id,'case_sha256':r['case_sha256'],
            'max_stress_mpa':r['results']['maximum_nodal_von_mises_mpa'],
            'max_displacement_mm':r['results']['maximum_displacement_mm'],
            'mesh_node_count':r['mesh']['node_count'],
            'mesh_tetrahedron_count':r['mesh']['tetrahedron_count']}
        return entry,actual
    def verify(self,entry,actual):
        return trust.verified_archive_summary(entry,'f'*32,None,None,archive_verifier=lambda *args: actual)
    def test_real_archive_matches_without_silent_replacement(self):
        entry,actual=self.sample();old=copy.deepcopy(entry)
        out=self.verify(entry,actual)
        self.assertEqual(out,old);self.assertEqual(entry,old)
    def test_saved_stress_modified_fails_closed(self):
        entry,actual=self.sample();entry['fea']['maximum_von_mises_mpa']+=1
        out=self.verify(entry,actual)
        self.assertEqual(out['fea']['state'],'failed')
        self.assertNotIn('maximum_von_mises_mpa',out['fea'])
        self.assertNotIn('field_visualization',out['fea'])
    def test_saved_displacement_modified_fails_closed(self):
        entry,actual=self.sample();entry['fea']['maximum_displacement_mm']*=2
        self.assertEqual(self.verify(entry,actual)['fea']['state'],'failed')
    def test_saved_mesh_count_modified_fails_closed(self):
        entry,actual=self.sample();entry['fea']['node_count']+=1
        self.assertEqual(self.verify(entry,actual)['fea']['state'],'failed')
    def test_invalid_fea_report_numbers_fails_closed(self):
        entry,actual=self.sample();entry['fea']['maximum_von_mises_mpa']=float('nan')
        self.assertEqual(self.verify(entry,actual)['fea']['state'],'failed')
    def test_wrong_case_and_run_rejected(self):
        for key in ('case_sha256','run_id','cad_sha256'):
            entry,actual=self.sample();actual[key]='a'*64
            self.assertEqual(self.verify(entry,actual)['fea']['state'],'failed')
    def test_partial_task_does_not_leak_stale_field(self):
        for state in ('running','queued','failed'):
            task={'status':state,'result':{'results':{'maximum_nodal_von_mises_mpa':777}},
                  'field':{'stress':[777]},'surface_field':{'x':1},
                  'field_visualization':{'available':True},'source_validation':'INP_STA_FRD_reverified'}
            out=trust.reverify_task_for_display(task,None,None,'unused')
            self.assertEqual(out['status'],state)
            for k in ('result','field','surface_field','field_visualization','source_validation'):
                self.assertNotIn(k,out)
            self.assertIn('result',task)
    def test_archived_failed_state_suppresses_stale_numbers(self):
        entry,_=self.sample();entry['fea']['state']='failed'
        out=self.verify(entry,None)
        self.assertNotIn('maximum_displacement_mm',out['fea'])
        self.assertNotIn('field_visualization',out['fea'])
    def test_corrupt_report_type_refused(self):
        entry,_=self.sample();entry['fea']=['invalid']
        with self.assertRaises(ValueError):self.verify(entry,None)

class QA7Preservation(unittest.TestCase):
    def test_ml_weights_byte_identical_to_qa6(self):
        name='ml/r12_research/research_model.joblib'
        old=(ORIG/'payload'/name).read_bytes();new=(ROOT/'payload'/name).read_bytes()
        self.assertEqual(new,old)
        self.assertEqual(hashlib.sha256(new).hexdigest(),'df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0')
    def test_solver_and_3d_frontend_byte_identical_to_qa6(self):
        for name in ('fea_solver.py','frontend/index.html','ml_r12_bridge.py'):
            with self.subTest(name=name):
                self.assertEqual((ORIG/'payload'/name).read_bytes(),(ROOT/'payload'/name).read_bytes())
    def test_qa7_only_changes_trust_module_and_installer_metadata(self):
        # Historical QA7 regression must compare its original archive, not the
        # evolving QA8 working tree (whose backend intentionally changed).
        with zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA6_메시연구기록_교차검증_통합보관본.zip') as old_zip, \
             zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA7_전체회귀_결과신뢰성_통합보관본.zip') as qa7_zip:
            for f in json.loads(qa7_zip.read('manifest.json'))['files']:
                if f=='fea_result_trust_gate.py':continue
                self.assertEqual(old_zip.read('payload/'+f),qa7_zip.read('payload/'+f),f)

class QA7MeshContract(unittest.TestCase):
    def test_three_mesh_case_signatures_distinct(self):
        spec=importlib.util.spec_from_file_location('qa7_mesh',ROOT/'fea_mesh_series.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        original={'cad_sha256':'a'*64,'mesh_request':{'target_element_size_mm':3.0},
                  'preset_metadata':{},'boundary_conditions':{'total_force_n':29.41995}}
        before=copy.deepcopy(original)
        cases=m.mesh_cases(original)
        self.assertEqual(original,before)
        self.assertEqual([c['mesh_request']['target_element_size_mm'] for c in cases],[4.2,3.0,2.25])
        self.assertEqual(len({c['case_sha256'] for c in cases}),3)
        self.assertEqual([c['boundary_conditions']['total_force_n'] for c in cases],[29.41995]*3)

if __name__=='__main__':unittest.main(verbosity=2)

class QA7UpgradeFromQA6(unittest.TestCase):
    def test_qa6_to_qa8_cumulative_update_and_rolls_back(self):
        import zipfile
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('qa7_installer', ROOT / 'installer.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);runtime=home/'GeoFieldCAD'/'onefile_runtime'/'8a9ac53a821a0eb5'
            runtime.mkdir(parents=True)
            with zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA6_메시연구기록_교차검증_통합보관본.zip') as z:
                for item in json.loads((ROOT/'manifest.json').read_text())['files']:
                    data= (ORIG/'fea_result_trust_gate.py').read_bytes() if item=='fea_result_trust_gate.py' else z.read('payload/'+item)
                    p=runtime/item;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            (runtime/'engine_runtime.py').write_text('# existing runtime dependency\n')
            keep={'engineering/L_bracket.step':b'STEP-CONTENT',
                  'history.sqlite':b'SQLITE-CONTENT',
                  'fea_runs/run1/geofield_case.frd':b'FRD-CONTENT',
                  'ml/existing_weights.pt':b'ML-CONTENT'}
            for name,data in keep.items():
                p=runtime/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            old=(runtime/'fea_result_trust_gate.py').read_bytes()
            receipt={}
            result=m.apply(m.DirectoryBundle(ROOT),localappdata=home,receipt=receipt)
            self.assertEqual(result,0)
            self.assertEqual([x['path'] for x in receipt['changed']],['GeoField_CAD_Analysis.py','frontend/cad.js','fea_result_trust_gate.py'])
            self.assertEqual(m.apply(m.DirectoryBundle(ROOT),localappdata=home),0)
            for name,data in keep.items():self.assertEqual((runtime/name).read_bytes(),data)
            self.assertEqual(m.rollback_install(receipt),3)
            self.assertEqual((runtime/'fea_result_trust_gate.py').read_bytes(),old)
            for name,data in keep.items():self.assertEqual((runtime/name).read_bytes(),data)
    def test_unknown_existing_trust_module_refuses_update(self):
        spec=importlib.util.spec_from_file_location('qa7_installer_unknown', ROOT / 'installer.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);runtime=home/'GeoFieldCAD'/'onefile_runtime'/'8a9ac53a821a0eb5'
            runtime.mkdir(parents=True)
            for f in json.loads((ROOT/'manifest.json').read_text())['files']:
                p=runtime/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/'payload'/f).read_bytes())
            (runtime/'fea_result_trust_gate.py').write_text('# UNKNOWN USER EDIT\n')
            (runtime/'engine_runtime.py').write_text('# existing runtime dependency\n')
            with self.assertRaisesRegex(RuntimeError,'Refusing to overwrite unknown source'):
                m.apply(m.DirectoryBundle(ROOT),localappdata=home)
            self.assertEqual((runtime/'fea_result_trust_gate.py').read_text(),'# UNKNOWN USER EDIT\n')
