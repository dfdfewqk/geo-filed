"""QA5 self-contained read-only regression checks. No Windows solver, CAD, or DB writes."""
import ast,copy,json,math,re,sys,tempfile,types,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'payload'/'GeoField_CAD_Analysis.py'
EVIDENCE=Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')

class QATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='r125_reconcile_current_fea_summary']
        assert len(functions)==1
        code=compile(ast.Module(body=functions,type_ignores=[]),str(SOURCE),'exec')
        scope={'valid_uid':lambda x:isinstance(x,str) and re.fullmatch('[0-9a-f]{32}',x) is not None}
        exec(code,scope)
        cls.guard=staticmethod(scope['r125_reconcile_current_fea_summary'])
        assert EVIDENCE.is_file(),'Actual independent FRD archive is needed for this regression'
        with zipfile.ZipFile(EVIDENCE) as z:
            root='09ef27cabe074bfa84b413d786fe075e/'
            cls.result=json.loads(z.read(root+'result.json'))
            cls.case=json.loads(z.read(root+'case.json'))
            cls.field=json.loads(z.read(root+'geofield_fea_surface_field.json'))
            cls.frd=z.read(root+'geofield_case.frd')
            cls.inp=z.read(root+'geofield_case.inp')
    def sample(self):
        rid='09ef27cabe074bfa84b413d786fe075e'
        res=self.result
        task={'id':rid,'status':'complete','source_validation':'INP_STA_FRD_reverified',
              'cad_sha256':res['cad_sha256'],'case_sha256':res['case_sha256'], 'result':copy.deepcopy(res)}
        summary={'cad':{'sha256':res['cad_sha256']},'fea':{
            'state':'complete','result_run_id':rid,'result_case_sha256':res['case_sha256'],
            'maximum_von_mises_mpa':res['results']['maximum_nodal_von_mises_mpa'],
            'maximum_displacement_mm':res['results']['maximum_displacement_mm'],
            'node_count':res['mesh']['node_count'],
            'tetrahedron_count':res['mesh']['tetrahedron_count']}}
        provenance={'source_verification':'INP_STA_FRD_reverified','verified_run_id':rid,
                    'solved_case_sha256':res['case_sha256']}
        return summary,task,provenance
    def checked(self,mutate=None):
        summ,task,proof=self.sample()
        if mutate:mutate(summ,task,proof)
        self.guard(summ,task,proof,self.result['cad_sha256'])
        return summ,task,proof
    def test_unmodified_actual_archive_all_numbers(self):
        s,_,p=self.checked();self.assertEqual(s['fea']['state'],'complete');self.assertTrue(p['summary_numbers_crosschecked'])
    def test_stress_modified_rejected(self):
        s,_,p=self.checked(lambda s,t,p:s['fea'].__setitem__('maximum_von_mises_mpa',20.0))
        self.assertEqual(s['fea']['state'],'rejected');self.assertNotIn('maximum_von_mises_mpa',s['fea']);self.assertIsNone(p['verified_run_id'])
    def test_displacement_modified_rejected(self):
        s,_,_=self.checked(lambda s,t,p:s['fea'].__setitem__('maximum_displacement_mm',0.42));self.assertEqual(s['fea']['state'],'rejected')
    def test_mesh_count_modified_rejected(self):
        s,_,_=self.checked(lambda s,t,p:s['fea'].__setitem__('node_count',2797));self.assertEqual(s['fea']['state'],'rejected')
    def test_result_run_id_modified_rejected(self):
        s,_,_=self.checked(lambda s,t,p:s['fea'].__setitem__('result_run_id','f'*32));self.assertEqual(s['fea']['state'],'rejected')
    def test_result_case_mismatch_rejected(self):
        s,_,_=self.checked(lambda s,t,p:t.__setitem__('case_sha256','0'*64));self.assertEqual(s['fea']['state'],'rejected')
    def test_provenance_mismatch_rejected(self):
        s,_,_=self.checked(lambda s,t,p:p.__setitem__('verified_run_id','f'*32));self.assertEqual(s['fea']['state'],'rejected')
    def test_reverify_missing_rejected(self):
        s,_,_=self.checked(lambda s,t,p:t.__setitem__('source_validation','not_verified'));self.assertEqual(s['fea']['state'],'rejected')
    def test_legacy_optional_ids_supported(self):
        s,_,_=self.checked(lambda s,t,p:[s['fea'].pop(k) for k in ('result_run_id','result_case_sha256')]);self.assertEqual(s['fea']['state'],'complete')
    def test_legacy_task_missing_hash_uses_reverified_result(self):
        s,_,_=self.checked(lambda s,t,p:t.pop('case_sha256'))
        self.assertEqual(s['fea']['state'],'complete')
    def test_non_complete_never_claims_verified(self):
        s,_,p=self.checked(lambda s,t,p:s['fea'].__setitem__('state','running'));self.assertEqual(s['fea']['state'],'running');self.assertNotIn('summary_numbers_crosschecked',p)
    def test_real_frd_and_field_match_archive_summary(self):
        # Independent FRD extraction using the existing source parser rather than stored result.json.
        inp=self.inp.decode('ascii');ids=set();active=False
        for line in inp.splitlines():
            line=line.strip()
            if line.upper().startswith('*NODE'):
                active=True;continue
            if active and line.startswith('*'):break
            if active and line and not line.startswith('**'):ids.add(int(line.split(',')[0]))
        self.assertEqual(len(ids),self.result['mesh']['node_count'])
        # Inject only missing runtime imports; fea_solver import itself is read-only.
        gravity=types.ModuleType('gravity_evidence');gravity.gravity_spec=lambda *a:None;gravity.gravity_input_validation=lambda *a:None
        engine=types.ModuleType('engine_runtime');engine.gmsh_python_status=lambda *a:None
        with patch.dict(sys.modules,{'gravity_evidence':gravity,'engine_runtime':engine}):
            import importlib.util
            spec=importlib.util.spec_from_file_location('qa5_solver',ROOT/'payload'/'fea_solver.py')
            solver=importlib.util.module_from_spec(spec);spec.loader.exec_module(solver)
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'actual.frd';path.write_bytes(self.frd)
                parsed=solver.parse_frd_results(path,ids,include_fields=True)
        n=self.result['results'];self.assertAlmostEqual(parsed['maximum_nodal_von_mises_mpa'],n['maximum_nodal_von_mises_mpa'],places=9)
        self.assertAlmostEqual(parsed['maximum_displacement_mm'],n['maximum_displacement_mm'],places=11)
        self.assertAlmostEqual(max(self.field['von_mises_mpa']),parsed['maximum_nodal_von_mises_mpa'],places=9)
        self.assertEqual(len(self.field['positions_mm']),len(self.field['von_mises_mpa']))
        self.assertEqual(len(self.field['positions_mm']),len(self.field['displacements_mm']))
    def test_no_test_field_overwrites_original(self):
        self.assertTrue(self.field['source']=='actual_calculix_ascii_frd')
        self.assertEqual(self.field['case_sha256'],self.case['case_sha256'])

if __name__=='__main__':unittest.main(verbosity=2)
