"""GeoField AI stage 8: full evidence-failure matrix against production functions.

These tests extract the real production handlers already covered in prior stage
tests. The test inputs are synthetic; no solver, API keys, network, STEP, FRD,
archive, SQLite or user data are touched.
"""
from __future__ import annotations
import copy
import math
import unittest

from test_agent_evidence import agent, record, CAD, CASE, RUN, JOB
from test_agent_fea_spatial import spatial, fea as spatial_fea, cad as spatial_cad
from test_agent_fea_spatial import field as spatial_field, features as spatial_features
from test_agent_fea_comparison import review as compare_review, comparison
from test_agent_restore_binding import context as restore_check, sample as restored_record
from test_agent_restore_binding import assert_current
from test_agent_llm import describe, ENV

class FullAgentFailureMatrix(unittest.TestCase):
    def check_fea_blocked(self, data):
        result=agent(*data)
        self.assertEqual(result['fea']['status'],'not_verified')
        self.assertIsNone(result['fea']['maximum_von_mises_mpa'])
        self.assertIsNone(result['fea']['maximum_displacement_mm'])
        self.assertIsNone(result['fea']['run_id'])
        self.assertFalse(result['fea']['safety_certified'])
        self.assertEqual(result['fea']['convergence'],'not_independently_verified')
        self.assertTrue(any(x['kind']=='cad' for x in result['findings']))
        return result

    def test_verified_fea_does_not_become_safety_or_convergence_proof(self):
        args=record();before=copy.deepcopy(args)
        out=agent(*args)
        self.assertEqual(args,before)
        self.assertEqual(out['fea']['status'],'INP_STA_FRD_reverified')
        self.assertEqual(out['fea']['element_type'],'C3D4')
        self.assertFalse(out['fea']['safety_certified'])
        self.assertEqual(out['fea']['convergence'],'not_independently_verified')
        self.assertFalse(out['ml']['used_for_structural_decision'])
        self.assertFalse(out['ml']['fea_calculated'])
        self.assertFalse(out['llm']['connected'])
        self.assertFalse(out['llm']['executed'])

    def test_optional_ml_states_do_not_change_real_fea(self):
        for state in ('queued','running','failed'):
            with self.subTest(state=state):
                args=list(record());args[2]['status']=state
                result=agent(*args)
                self.assertEqual(result['ml']['status'],state)
                self.assertEqual(result['fea']['maximum_von_mises_mpa'],14.512)
                self.assertEqual(result['fea']['maximum_displacement_mm'],.05698)

    def test_broken_ml_identifiers_do_not_overwrite_calculix(self):
        for field,value in (('cad_job_id','8'*32),('cad_sha256','f'*64),
                            ('id','not-a-valid-run')):
            with self.subTest(field=field):
                args=list(record());args[2][field]=value
                out=agent(*args)
                self.assertIn(out['ml']['status'],('identity_rejected','evidence_rejected'))
                self.assertEqual(out['fea']['status'],'INP_STA_FRD_reverified')
                self.assertEqual(out['fea']['run_id'],RUN)

    def test_ml_malformed_predictions_do_not_crash_fea(self):
        for invalid in ({'variants':[]},{'variants':{}},
                        {'variants':{'topology_trimmed':{'faces':None}}},
                        {'variants':{'topology_trimmed':{'faces':[None]}}}):
            with self.subTest(invalid=invalid):
                args=list(record());args[2]['result'].update(invalid)
                result=agent(*args)
                self.assertEqual(result['ml']['status'],'evidence_rejected')
                self.assertEqual(result['fea']['maximum_von_mises_mpa'],14.512)

    def test_missing_or_pending_fea_denies_all_numbers(self):
        for state in ('queued','running','failed'):
            with self.subTest(state=state):
                args=list(record());args[4]['status']=state
                self.check_fea_blocked(args)
        args=list(record());args[4]=None
        self.check_fea_blocked(args)

    def test_malformed_archive_fea_and_provenance_fail_closed(self):
        for attr,value in (('fea',[]),('fea',True),('fea','malformed'),
                           ('fea_case_provenance',[]),
                           ('fea_case_provenance',42),
                           ('fea_case_provenance','tampered')):
            with self.subTest(attr=attr,value=value):
                args=list(record());args[0][attr]=value
                self.check_fea_blocked(args)

    def test_fea_identity_source_and_mesh_mismatch_blocked(self):
        mutations=(
          lambda s,d,m,r,t: t.update(cad_job_id='f'*32),
          lambda s,d,m,r,t: t.update(cad_sha256='f'*64),
          lambda s,d,m,r,t: t.update(id='f'*32),
          lambda s,d,m,r,t: t.update(case_sha256='f'*64),
          lambda s,d,m,r,t: t.update(source_validation='unknown'),
          lambda s,d,m,r,t: t['result'].update(cad_sha256='f'*64),
          lambda s,d,m,r,t: t['result'].update(case_sha256='f'*64),
          lambda s,d,m,r,t: t['result']['mesh'].update(node_count=999),
          lambda s,d,m,r,t: t['result']['mesh'].update(tetrahedron_count=999),
          lambda s,d,m,r,t: t['result']['results'].update(maximum_nodal_von_mises_mpa=999),
          lambda s,d,m,r,t: s['fea_case_provenance'].update(verified_run_id='9'*32),
          lambda s,d,m,r,t: s['fea_case_provenance'].update(summary_numbers_crosschecked=False),
          lambda s,d,m,r,t: s['fea_case_provenance'].update(source_verification='cached_json'),
          lambda s,d,m,r,t: s['fea_case_provenance']['verified_mesh'].update(nodes=1),
        )
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                args=list(record());mutate(*args)
                self.check_fea_blocked(args)

    def test_corrupt_or_unverified_fea_numbers_blocked(self):
        for key in ('maximum_von_mises_mpa','maximum_displacement_mm'):
            for bad in (None,False,-1,float('inf'),float('nan'),[1],{'v':1}):
                with self.subTest(key=key,value=str(bad)):
                    args=list(record());args[0]['fea'][key]=bad
                    self.check_fea_blocked(args)

    def test_explicit_c3d4_c3d10_do_not_imply_other_element_type(self):
        for element in ('C3D4','C3D10'):
            args=list(record());args[4]['result']['mesh']['element_type']=element
            result=agent(*args)
            self.assertEqual(result['fea']['element_type'],element)
            self.assertFalse(result['fea']['safety_certified'])
        for malformed in (None,'C3D20',{},['C3D10'],'',False):
            with self.subTest(element=str(malformed)):
                args=list(record());args[4]['result']['mesh']['element_type']=malformed
                result=agent(*args)
                self.assertEqual(result['fea']['element_type'],'unverified')
                self.assertEqual(result['fea']['convergence'],'not_independently_verified')

    def test_stale_editable_fea_case_is_not_a_new_calculation(self):
        args=list(record())
        args[0]['fea_case_provenance'].update(result_matches_saved=False,
                                               result_matches_selected=False)
        out=agent(*args)
        self.assertEqual(out['fea']['status'],'INP_STA_FRD_reverified')
        self.assertTrue(any('선택·저장 조건' in f['title'] for f in out['findings']))
        self.assertFalse(out['fea']['safety_certified'])

    def test_r12_research_source_mismatch_keeps_real_fea(self):
        for field,bad in (('cad_sha256','f'*64),
                          ('mode','production_certified'),
                          ('fea_calculated',True)):
            with self.subTest(field=field):
                args=list(record());args[3][field]=bad
                out=agent(*args)
                self.assertIn(out['ml']['r12_status'],('identity_rejected','evidence_rejected'))
                self.assertEqual(out['fea']['maximum_von_mises_mpa'],14.512)

    def test_spatial_data_not_verified_never_links_cad_faces(self):
        bad=spatial_field();bad['cad_sha256']='f'*64
        result=spatial(spatial_fea(),spatial_cad(),bad,spatial_features())
        self.assertEqual(result['status'],'not_verified')
        self.assertFalse(result['cad_face_attribution_verified'])
        self.assertIsNone(result['stress_peak'])
        self.assertIsNone(result['displacement_peak'])

    def test_spatial_proximity_does_not_certify_risk(self):
        result=spatial(spatial_fea(),spatial_cad(),spatial_field(),spatial_features())
        self.assertEqual(result['status'],'verified_frd_surface_peak_positions')
        self.assertFalse(result['cad_face_attribution_verified'])
        self.assertEqual(result['stress_peak']['unit'],'MPa')
        self.assertNotEqual(result['stress_peak']['cad_face_proximity']['status'],
                            'verified_cad_face_attribution')

    def test_comparison_missing_original_is_not_improvement_proof(self):
        result=comparison()
        result['left']['evidence']='unverified_saved_json'
        out=compare_review(result)
        self.assertEqual(out['status'],'not_verified')
        self.assertFalse(out['causal_effect_verified'])
        self.assertFalse(out['structural_safety_verified'])

    def test_same_cad_mismatched_run_after_restart_denied(self):
        args=list(restored_record());args[0]['verified_restored_run_id']='9'*32
        self.assertEqual(restore_check(*args)['status'],'restore_evidence_not_verified')
        old=restored_record()[0];new=copy.deepcopy(old)
        new['verified_restored_case']['case_sha256']='e'*64
        with self.assertRaises(ValueError):
            assert_current(old,new)

    def test_llm_failure_stays_rules_only_and_never_mutates_fea(self):
        args=record();response=agent(*args);original=copy.deepcopy(response)
        def outage(*_):raise RuntimeError('network failure')
        result=describe(response,opt_in=True,environ=ENV,transport=outage)
        self.assertEqual(result['status'],'unavailable')
        self.assertFalse(result['executed'])
        self.assertFalse(result['connected'])
        self.assertEqual(response,original)

    def test_llm_without_consent_never_invokes_provider(self):
        response=agent(*record())
        calls=[]
        llm=describe(response,opt_in=False,environ=ENV,
                     transport=lambda *args:calls.append(args))
        self.assertEqual(calls,[])
        self.assertEqual(llm['status'],'rules_only')

if __name__=='__main__':
    unittest.main()
