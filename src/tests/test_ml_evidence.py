"""Research-only, CAD-bound ML -> agent evidence regression tests."""
import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
EVIDENCE=pathlib.Path(__import__('os').environ.get('GEOFIELD_TEST_ML_EVIDENCE_FILE',ROOT/'payload/ml_evidence.py'))
spec=importlib.util.spec_from_file_location('tested_ml_evidence',EVIDENCE)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
pack=module.build_evidence
select=module.select_current_task
CID='a'*32
SHA='b'*64
MODEL='c'*64

def base_r12():
    return {'id':'d'*32,'cad_job_id':CID,'cad_sha256':SHA,'status':'complete',
            'message':'R12 research model output',
            'result':{'cad_sha256':SHA,'status':'research_not_for_production',
                      'decision_usage':'blocked_diagnostic_only',
                      'is_independent_r12_research':True,'geometry_certified':False,
                      'fea_calculated':False,'candidate_count':1,
                      'predictions':[{'face_index':3,'predicted_hole_type':'unverified',
                                      'uncalibrated_model_score':.7,'status':'research_unverified',
                                      'decision_basis':'insufficient_brep_evidence'}]}}

class Contract(unittest.TestCase):
    def test_research_provenance_is_explicit(self):
        x=pack(CID,SHA,provider='r12',model_sha256=MODEL,task=base_r12())
        self.assertEqual(x['schema'],'geofield-ml-evidence-v1')
        self.assertEqual(x['model_sha256'],MODEL)
        self.assertTrue(x['research_only'])
        self.assertFalse(x['eligible_for_structural_decision'])
        self.assertFalse(x['geometry_certified'])
        self.assertFalse(x['fea_calculated'])
        self.assertEqual(x['predictions'][0]['predicted_hole_type'],'unverified')
    def test_completed_archive_metadata_for_agent(self):
        item=base_r12()
        item['completed_at']='2026-10-22T00:00:00+00:00'
        item['restored_from_run_id']='e'*32
        evidence=pack(CID,SHA,provider='r12',model_sha256=MODEL,task=item)
        self.assertEqual(evidence['model_version'],'r12-research-'+MODEL[:12])
        self.assertEqual(evidence['restored_from_run_id'],'e'*32)
        self.assertEqual(evidence['completed_at'],item['completed_at'])
        self.assertFalse(evidence['eligible_for_structural_decision'])
    def test_invalid_archive_run_id_rejected(self):
        item=base_r12()
        item['restored_from_run_id']='not-a-valid-uuid'
        with self.assertRaisesRegex(ValueError,'restored run ID'):
            pack(CID,SHA,provider='r12',model_sha256=MODEL,task=item)

    def test_foreign_cad_denied(self):
        d=base_r12();d['cad_sha256']='e'*64
        with self.assertRaisesRegex(ValueError,'different CAD'):pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)
    def test_result_sha_mismatch_denied(self):
        d=base_r12();d['result']['cad_sha256']='e'*64
        with self.assertRaisesRegex(ValueError,'provenance'):pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)
    def test_research_only_cannot_be_upgraded(self):
        d=base_r12();d['result']['geometry_certified']=True
        with self.assertRaises(ValueError):pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)
    def test_tampered_score_rejected(self):
        d=base_r12();d['result']['predictions'][0]['uncalibrated_model_score']=float('nan')
        with self.assertRaises(ValueError):pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)
    def test_failed_ml_does_not_invent_predictions(self):
        d=base_r12();d['status']='failed';d.pop('result')
        x=pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)
        self.assertEqual(x['status'],'failed');self.assertEqual(x['predictions'],[])
    def test_absent_ml_unavailable_to_agent(self):
        d=pack(CID,SHA)
        self.assertEqual(d['provider'],'none');self.assertEqual(d['status'],'not_run')
    def test_brepmfr_face_research(self):
        data={'id':'d'*32,'cad_job_id':CID,'cad_sha256':SHA,'status':'complete',
              'result':{'sha256':SHA,'decision_usage':'blocked_diagnostic_only',
                        'variants':{'topology_trimmed':{'faces':[{'face_ordinal':2,'model_class':'unverified',
                                                                 'model_score_uncalibrated':.22,'geometry_surface':'CYLINDER'}]}}}}
        x=pack(CID,SHA,provider='brepmfr',model_sha256=MODEL,task=data)
        self.assertEqual(x['provider'],'brepmfr');self.assertEqual(len(x['predictions']),1)
        self.assertFalse(x['eligible_for_structural_decision'])
    def test_current_successful_r12_over_failed_brepmfr(self):
        failed={'id':'d'*32,'cad_job_id':CID,'cad_sha256':SHA,'automatic':True,'status':'failed'}
        research=base_r12()
        research['id']='e'*32
        research['automatic']=True
        provider,chosen=select(CID,SHA,'e'*32,[failed],[research])
        self.assertEqual(provider,'r12')
        self.assertEqual(chosen['id'],'e'*32)
        self.assertEqual(pack(CID,SHA,task=chosen,provider=provider,model_sha256=MODEL)['status'],'complete')

    def test_active_brepmfr_over_old_r12(self):
        research=base_r12()
        research['automatic']=True
        brep={'id':'f'*32,'cad_job_id':CID,'cad_sha256':SHA,'automatic':True,
              'status':'running'}
        p,t=select(CID,SHA,'f'*32,[brep],[research])
        self.assertEqual((p,t['status']),('brepmfr','running'))

    def test_no_fallback_to_old_success_when_selected_run_missing(self):
        research=base_r12()
        research['automatic']=True
        self.assertIsNone(select(CID,SHA,'f'*32,[],[research]))
        self.assertIsNone(select(CID,SHA,None,[],[research]))

    def test_never_select_foreign_cad_or_forged_sha(self):
        research=base_r12();research['automatic']=True
        self.assertIsNone(select(CID,SHA,'d'*32,[],[{**research,'cad_sha256':'e'*64}]))
        self.assertIsNone(select(CID,SHA,'d'*32,[],[{**research,'cad_job_id':'e'*32}]))

    def test_manual_result_allowed_only_without_auto_run_id(self):
        research=base_r12();research.pop('automatic',None)
        self.assertEqual(select(CID,SHA,None,[],[research])[0],'r12')
        self.assertIsNone(select(CID,SHA,'d'*32,[],[research]))

    def test_ambiguous_active_id_must_fail_closed(self):
        one=base_r12();one['automatic']=True
        two={**one}
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            select(CID,SHA,'d'*32,[two],[one])

    def test_invalid_active_run_id_rejected(self):
        with self.assertRaisesRegex(ValueError,'run identity'):
            select(CID,SHA,'not-an-id',[],[])

    def test_unavailable_and_failed_without_false_predictions(self):
        for state in ('unavailable','failed','disabled_by_user'):
            with self.subTest(state=state):
                evidence=pack(CID,SHA,status=state,message='missing dependencies')
                self.assertEqual(evidence['status'],state)
                self.assertEqual(evidence['provider'],'none')
                self.assertEqual(evidence['predictions'],[])
                self.assertFalse(evidence['eligible_for_structural_decision'])

    def test_invalid_no_task_state_rejected(self):
        with self.assertRaisesRegex(ValueError,'unavailable ML evidence state'):
            pack(CID,SHA,status='complete')

    def test_task_checkpoint_provenance_mismatch_rejected(self):
        d=base_r12();d['model_sha256']='e'*64
        with self.assertRaisesRegex(ValueError,'checkpoint SHA'):
            pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)

    def test_task_model_version_mismatch_rejected(self):
        d=base_r12();d['model_version']='r12-research-'+'e'*12
        with self.assertRaisesRegex(ValueError,'model version'):
            pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)

    def test_task_provider_mismatch_rejected(self):
        d=base_r12();d['provider']='brepmfr'
        with self.assertRaisesRegex(ValueError,'provider'):
            pack(CID,SHA,provider='r12',model_sha256=MODEL,task=d)

    def test_server_has_readonly_evidence_endpoint(self):
        server=pathlib.Path(__import__('os').environ.get('GEOFIELD_TEST_SERVER_FILE',ROOT/'payload/GeoField_CAD_Analysis.py')).read_text(encoding='utf8')
        self.assertIn("if path.startswith('/api/ml/evidence/')",server)
        self.assertIn("if active!=uid or job.get('status')!='complete'",server)

if __name__=='__main__':unittest.main()
