"""QA9: original 3kg INP force/moment audit and non-fabricated three-mesh diagnostic.

Actual archived CalculiX INP/FRD are preserved byte for byte. Any changed
input is a disposable test copy, not a new solver execution.
"""
import ast, copy, hashlib, importlib.util, json, math, re, tempfile, unittest, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'payload'/'GeoField_CAD_Analysis.py').read_text(encoding='utf-8')
TREE=ast.parse(SOURCE)
FUNCTIONS=('r1220_verified_inp_load_markers','qa9_compare_actual_mesh_loads','r1213_verified_mesh_spatial_study')
NODES=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS]
assert len(NODES)==3
ENV={'Path':Path}
exec(compile(ast.Module(body=NODES,type_ignores=[]),str(ROOT/'payload'/'GeoField_CAD_Analysis.py'),'exec'),ENV)
load_markers=ENV['r1220_verified_inp_load_markers']
compare=ENV['qa9_compare_actual_mesh_loads']
study=ENV['r1213_verified_mesh_spatial_study']
REAL_ZIP=Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')
REAL_STEP=Path('/mnt/data/files/L_bracket.step')


def recorded_deck_and_case():
    if not REAL_ZIP.is_file():raise unittest.SkipTest('actual 3kg CalculiX archive not present')
    with zipfile.ZipFile(REAL_ZIP) as bundle:
        path=next(n for n in bundle.namelist() if n.endswith('/geofield_case.inp'))
        root=path.rsplit('/',1)[0]
        return bundle.read(path),json.loads(bundle.read(root+'/case.json'))


class ActualInpTests(unittest.TestCase):
    def setUp(self):
        deck,case=recorded_deck_and_case()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.deck=Path(self.temp.name)/'verified.inp';self.deck.write_bytes(deck)
        self.case=case;self.source=deck

    def audit(self):return load_markers(self.deck,self.case)

    def test_archived_step_matches_actual_calculix_case(self):
        if not REAL_STEP.is_file():self.skipTest('Original STEP unavailable')
        self.assertEqual(hashlib.sha256(REAL_STEP.read_bytes()).hexdigest(),self.case['cad_sha256'])

    def test_force_center_and_moment_are_independently_reconstructed(self):
        result=self.audit()
        self.assertEqual(result['applied_node_count'],609)
        self.assertEqual(result['shown_node_count'],24)
        self.assertAlmostEqual(result['total_force_n'][2],-29.41995,places=5)
        self.assertAlmostEqual(result['force_application_center_mm'][0],25.389742,places=5)
        self.assertAlmostEqual(result['force_application_center_mm'][1],0.00480923,places=6)
        self.assertAlmostEqual(result['moment_about_global_origin_n_mm'][1],746.96494,places=4)
        self.assertAlmostEqual(result['moment_about_global_origin_n_mm'][0],-0.14148727,places=5)
        self.assertEqual(self.deck.read_bytes(),self.source)

    def test_inp_force_sum_changed_is_rejected(self):
        contents=self.deck.read_text(encoding='ascii')
        # Mutate just the first actual CLOAD numeric value in this TEST copy.
        before,section=contents.split('*CLOAD\n',1)
        first,rest=section.split('\n',1)
        items=first.split(',')
        self.assertEqual(len(items),3)
        items[2]=str(float(items[2])*2)
        self.deck.write_text(before+'*CLOAD\n'+','.join(items)+'\n'+rest,encoding='ascii')
        with self.assertRaisesRegex(ValueError,'합력'):
            self.audit()

    def test_inp_opposing_same_sum_not_accepted(self):
        # Replace one load with a negative signed force, then compensate by
        # increasing a second force. The resultant remains unchanged.
        contents=self.deck.read_text(encoding='ascii')
        before,cload=contents.split('*CLOAD\n',1)
        cload_rows,after=cload.split('\n*NODE FILE',1)
        rows=cload_rows.strip().splitlines()
        a=[p.strip() for p in rows[0].split(',')]
        b=[p.strip() for p in rows[1].split(',')]
        aval=float(a[2]);a[2]=str(-aval);b[2]=str(float(b[2])+2*aval)
        rows[0]=', '.join(a);rows[1]=', '.join(b)
        self.deck.write_text(before+'*CLOAD\n'+'\n'.join(rows)+'\n*NODE FILE'+after,encoding='ascii')
        with self.assertRaisesRegex(ValueError,'방향'):
            self.audit()

    def test_multiple_identical_records_are_not_3_real_meshes(self):
        # This tests only the diagnostic helper's geometry math, never asserts
        # that running 3 identical copies proves mesh convergence.
        row=self.audit()
        comparison=compare([row,row,row])
        self.assertTrue(comparison['moment_shift_within_review_screen'])
        self.assertEqual(comparison['moment_step_changes_n_mm'],[0,0])
        self.assertFalse(comparison['convergence_certified'])


class StudyMomentComparabilityTests(unittest.TestCase):
    def setUp(self):
        r={'applied_node_count':500,'total_force_n':[0.,0.,-100.],
           'force_application_center_mm':[25.,0.,0.],
           'moment_about_global_origin_n_mm':[0.,2500.,0.]}
        self.samples=[copy.deepcopy(r) for _ in range(3)]

    def test_constant_moment_is_only_a_screen_not_certification(self):
        out=compare(self.samples)
        self.assertTrue(out['mesh_only_attribution_supported_by_this_screen'])
        self.assertFalse(out['convergence_certified'])
        self.assertEqual(out['review_screen_threshold_mm'],0.1)

    def test_nominal_force_preserved_but_0p3mm_moment_shift_is_flagged(self):
        r=self.samples[1]
        r['force_application_center_mm'][0]+=0.3
        r['moment_about_global_origin_n_mm'][1]+=30
        out=compare(self.samples)
        self.assertFalse(out['moment_shift_within_review_screen'])
        self.assertAlmostEqual(out['moment_equivalent_lever_arm_step_mm'][0],0.3)
        self.assertIn('모멘트 차이',out['warning'])

    def test_different_resultants_are_rejected(self):
        self.samples[2]['total_force_n'][2]=-90
        with self.assertRaisesRegex(ValueError,'합력'):
            compare(self.samples)

    def test_invalid_nan_bool_and_missing_data_are_rejected(self):
        for value in (float('nan'),True,None):
            rows=copy.deepcopy(self.samples)
            rows[0]['moment_about_global_origin_n_mm'][0]=value
            with self.assertRaises(ValueError):compare(rows)
        with self.assertRaises(ValueError):compare(self.samples[:2])

    def test_compare_does_not_mutate_rows(self):
        before=copy.deepcopy(self.samples)
        compare(self.samples)
        self.assertEqual(self.samples,before)


class StudyWireChecks(unittest.TestCase):
    def test_actual_inp_audit_is_after_independent_restoration(self):
        src=ast.get_source_segment(SOURCE,next(n for n in NODES if n.name=='r1213_verified_mesh_spatial_study'))
        self.assertLess(src.index('restore_payload('),src.index('r1220_verified_inp_load_markers('))
        self.assertIn("JOBS_DIR/'fea_runs'/actual_run/'geofield_case.inp'",src)
        self.assertIn('qa9_compare_actual_mesh_loads(load_rows)',src)
        self.assertIn("'status':'not_evaluable'",src)

    def test_study_exposes_actual_warning_without_amending_solver_results(self):
        sha='f'*64
        ids=['1'*32,'2'*32,'3'*32]
        runids=['a'*32,'b'*32,'c'*32]
        runs=[{'snapshot_id':i,'run_id':rid,'mesh_target_mm':size}
              for i,rid,size in zip(ids,runids,[4.,3.,2.])]
        analysis={'status':'verified_three_mesh_sensitivity_only','same_physical_case':True,
                  'solver_evidence':'each_calculix_run_revalidated','runs_coarse_to_fine':runs,
                  'warning':'원래 메시 품질 점검 안내'}
        cad={'sha':sha,'case':{'case_sha256':'e'*64,'self_weight_reference':{'applied_to_solver':False}}}
        old_env=dict(ENV)
        try:
            ENV.update({'HISTORY_DB':'unused','JOBS_DIR':Path('/tmp/test-only'),
                        'valid_uid':lambda value:isinstance(value,str) and bool(re.fullmatch(r'[0-9a-f]{32}',value)),
                        'assess_verified_mesh_study':lambda db,jobs,snapshots:copy.deepcopy(analysis),
                        'r184_verified_archive_numbers':lambda sid:{'cad_job_id':'0'*32,'run_id':runids[ids.index(sid)],'cad_sha256':sha,'case_sha256':'e'*64},
                        'restore_payload':lambda jobs,uid,run_hint:(cad,run_hint,{'case_sha256':'e'*64,'results':{'maximum_nodal_von_mises_mpa':10.}},None),
                        'r185_verified_archive_field':lambda sid:{'run_id':runids[ids.index(sid)],'cad_sha256':sha,'case_sha256':'e'*64,
                            'field':{'positions_mm':[[1.,2.,3.]],'von_mises_mpa':[9.]}},
                        'r1220_verified_inp_load_markers':lambda path,case: {
                            'applied_node_count':500,'total_force_n':[0.,0.,-100.],
                            'force_application_center_mm':[25. + (0.3 if runids[1] in str(path) else 0),0.,0.],
                            'moment_about_global_origin_n_mm':[0.,2530. if runids[1] in str(path) else 2500.,0.]},
                        })
            out=study(ids)
            self.assertEqual(out['actual_load_moment_diagnostic']['status'],'evaluated_from_three_verified_inp_decks')
            self.assertFalse(out['mesh_only_attribution_supported_by_this_screen'])
            self.assertIn('0.3000mm',out['warning'])
            self.assertIn('원래 메시 품질 점검 안내',out['warning'])
            self.assertFalse(out['convergence_certified'])
        finally:
            ENV.clear();ENV.update(old_env)

    def test_study_missing_inp_is_explicitly_not_evaluable(self):
        ids=['1'*32,'2'*32,'3'*32]
        runs=[{'snapshot_id':sid,'run_id':chr(97+i)*32,'mesh_target_mm':4.-i} for i,sid in enumerate(ids)]
        analysis={'status':'verified_three_mesh_sensitivity_only','same_physical_case':True,
                  'solver_evidence':'each_calculix_run_revalidated','runs_coarse_to_fine':runs,'warning':''}
        sha='a'*64
        case={'case_sha256':'b'*64,'self_weight_reference':{'applied_to_solver':False}}
        old_env=dict(ENV)
        try:
            ENV.update({'HISTORY_DB':'none','JOBS_DIR':Path('/tmp/qa9-test-absent'),
                'valid_uid':lambda v:isinstance(v,str) and bool(re.fullmatch(r'[0-9a-f]{32}',v)),
                'assess_verified_mesh_study':lambda *args:copy.deepcopy(analysis),
                'r184_verified_archive_numbers':lambda sid:{'cad_job_id':'0'*32,'run_id':runs[ids.index(sid)]['run_id'],
                    'cad_sha256':sha,'case_sha256':'b'*64},
                'restore_payload':lambda jobs,uid,run_hint:({'sha':sha,'case':case},run_hint,
                    {'case_sha256':'b'*64,'results':{'maximum_nodal_von_mises_mpa':1.}},None),
                'r185_verified_archive_field':lambda sid:{'run_id':runs[ids.index(sid)]['run_id'],
                    'cad_sha256':sha,'case_sha256':'b'*64,'field':{'positions_mm':[[1.,2.,3.]],'von_mises_mpa':[1.]}},
                'r1220_verified_inp_load_markers':lambda path,case:(_ for _ in ()).throw(FileNotFoundError('INP 없음'))})
            out=study(ids)
            self.assertEqual(out['actual_load_moment_diagnostic']['status'],'not_evaluable')
            self.assertFalse(out['mesh_only_attribution_supported_by_this_screen'])
            self.assertIn('INP 없음',out['warning'])
            self.assertFalse(out['convergence_certified'])
        finally:
            ENV.clear();ENV.update(old_env)

    def test_missing_inp_cannot_pass_load_comparability_screen(self):
        # Ensures fail-closed public fields on actual study function source.
        source=ast.get_source_segment(SOURCE,next(n for n in NODES if n.name=='r1213_verified_mesh_spatial_study'))
        self.assertIn("'mesh_only_attribution_supported_by_this_screen':False",source)
        self.assertIn("'actual_load_moment_diagnostic':load_diagnostic",source)


class InstallerUpgradeTest(unittest.TestCase):
    def test_qa8_to_qa9_one_backend_change_and_rollback(self):
        src=Path('/mnt/data/GeoField_R12_13_QA8_CAD_FEA_원본교차검증_통합보관본.zip')
        if not src.is_file():self.skipTest('previous QA8 zip missing')
        spec=importlib.util.spec_from_file_location('qa9_installer',ROOT/'installer.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as d:
            temp=Path(d);runtime=temp/'GeoFieldCAD'/'onefile_runtime'/'8a9ac53a821a0eb5'
            runtime.mkdir(parents=True)
            with zipfile.ZipFile(src) as z:
                for rel in json.loads((ROOT/'manifest.json').read_text())['files']:
                    f=runtime/rel;f.parent.mkdir(parents=True,exist_ok=True)
                    f.write_bytes(z.read('payload/'+rel))
            (runtime/'engine_runtime.py').write_text('# existing runtime')
            saved={'source/L_bracket.step':b'untouched cad', 'history/results.sqlite3':b'untouched db',
                   'fea_runs/old/geofield_case.frd':b'untouched frd',
                   'fea_runs/old/geofield_case.inp':b'untouched inp',
                   'ml/old/model.pt':b'untouched ML'}
            for rel,data in saved.items():
                f=runtime/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
            old_backend=(runtime/'GeoField_CAD_Analysis.py').read_bytes()
            receipt={}
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=temp,receipt=receipt),0)
            self.assertEqual([x['path'] for x in receipt['changed']],['GeoField_CAD_Analysis.py','frontend/cad.js'])
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=temp),0)
            self.assertEqual(installer.rollback_install(receipt),2)
            self.assertEqual(old_backend,(runtime/'GeoField_CAD_Analysis.py').read_bytes())
            for rel,data in saved.items():self.assertEqual((runtime/rel).read_bytes(),data)


if __name__=='__main__':unittest.main()
