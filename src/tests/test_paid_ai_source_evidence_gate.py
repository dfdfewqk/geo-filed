"""Paid GeoField AI evidence: no provider tokens without complete original sources.

Exercises production preflight function via AST with synthetic immutable JSON.
No STEP, FRD, browser, solver, SQLite write, API keys or external requests.
"""
import ast
import copy
import json
import unittest
from pathlib import Path

import ml_r12_bridge

SOURCE=Path(__file__).resolve().parents[1]/'payload'/'GeoField_CAD_Analysis.py'
TEXT=SOURCE.read_text(encoding='utf-8')
FUNCTION=next(node for node in ast.parse(TEXT).body
              if isinstance(node,ast.FunctionDef) and
              node.name=='gf_paid_ai_preflight')
CONTEXT={'ml_r12_bridge':ml_r12_bridge}
exec(compile(ast.Module(body=[FUNCTION],type_ignores=[]),str(SOURCE),'exec'),CONTEXT)
check=CONTEXT['gf_paid_ai_preflight']

SHA='a'*64
CASE='b'*64
UID='1'*32
RUN='2'*32
MLID='3'*32
R12ID='4'*32
def fixture():
    raw_ml={'status':'complete','id':MLID,'cad_job_id':UID,'cad_sha256':SHA,
      'result':{'sha256':SHA,'decision_usage':'blocked_diagnostic_only',
        'variants':{'topology_trimmed':{'faces':[
          {'face_ordinal':0,'geometry_surface':'Cylinder','model_class':'hole',
           'model_score_uncalibrated':.47},
          {'face_ordinal':1,'geometry_surface':'Plane','model_class':'non_hole',
           'model_score_uncalibrated':.91}]}}}}
    prediction={'face_index':0,'uncalibrated_model_score':.6,
        'raw_ml_top_class':'through_hole','raw_ml_thresholded':'through_hole',
        'predicted_hole_type':'through_hole',
        'topology_evidence':'through_hole',
        'decision_basis':'model_and_brep_topology_agree',
        'status':'research_unverified'}
    raw_r12={'status':'complete','id':R12ID,'cad_job_id':UID,'cad_sha256':SHA,
      'result':{'cad_sha256':SHA,'decision_usage':'blocked_diagnostic_only',
          'status':'research_not_for_production','fea_calculated':False,
          'geometry_certified':False,'is_independent_r12_research':True,
          'candidate_count':1,'predictions':[prediction]}}
    agent={'schema':'geofield-evidence-agent-v1','cad_sha256':SHA,
      'cad':{'job_id':UID,'findings_count':2},
      'input_contract':{'r12':{'status':'research_complete'}},
      'cad_features':{
        'schema':'geofield-agent-cad-features-v1','cad_sha256':SHA,
        'cad_job_id':UID,'mapping_source':'current_cad_mesh_triangles_only',
        'ml_face_ordinals_are_cad_face_ids':False,'fea_hotspots_verified':False,
        'candidate_count':1,'candidates':[{
          'source':'cad_brep_rule_review','face_mapping_status':'verified_in_current_cad_mesh',
          'mechanical_risk_confirmed':False}]},
      'hole_geometry_summary':{
        'source':'local_ocp_solid_occupancy_not_ml','status':'complete',
        'through_cylindrical_face_count':4,'blind_cylindrical_face_count':0,
        'unverified_cylindrical_face_count':0,
        'unique_drilled_hole_count_verified':False,'mechanical_cause_verified':False},
      'ml':{'status':'research_unverified','run_id':MLID,
         'candidate_count':2,'r12_candidate_count':1,
         'cad_comparison':{'status':'aggregate_only_no_face_correspondence',
           'face_mapping_verified':False,'cad_fea_conclusion_allowed':False}},
      'fea':{'status':'INP_STA_FRD_reverified','run_id':RUN,
         'case_sha256':CASE,'maximum_von_mises_mpa':14.758,
         'maximum_displacement_mm':.0264,'nodes':1200,'tetrahedra':4400,
         'element_type':'C3D4'},
      'fea_spatial':{'schema':'geofield-agent-fea-spatial-v1',
         'status':'verified_frd_surface_peak_positions','cad_sha256':SHA,
         'case_sha256':CASE,'run_id':RUN,'cad_face_attribution_verified':False,
         'stress_peak':{'source':'reverified_actual_calculix_surface_nodes',
           'unit':'MPa','value':13.5,'position_mm':[10.,20.,30.]},
         'displacement_peak':{'source':'reverified_actual_calculix_surface_nodes',
           'unit':'mm','value':.021,'position_mm':[30.,20.,10.]}},
      'engineering_context':{
         'source':'verified_fea_case_numeric_only',
         'young_modulus_mpa':200000.,'poisson_ratio':.3,
         'applied_force_n':49.05,'force_direction_unit':[0.,0.,-1.],
         'fixed_face_count':1,'loaded_face_count':1,
         'target_mesh_size_mm':1.833,'stress_location_cause_verified':False},
      'mesh_followup_context':{
         'source':'three_independently_reverified_calculix_runs',
         'status':'verified_mesh_sensitivity_only','same_physical_case':True,
         'convergence_certified':False,'safety_certified':False,
         'runs_coarse_to_fine':[
            {'target_mesh_mm':3.,'max_stress_mpa':12.,'max_displacement_mm':.02},
            {'target_mesh_mm':2.,'max_stress_mpa':13.,'max_displacement_mm':.022},
            {'target_mesh_mm':1.,'max_stress_mpa':13.5,'max_displacement_mm':.023}],
         'adjacent_relative_change_percent':[
            {'stress_percent':7.6923077,'displacement_percent':9.0909091},
            {'stress_percent':3.7037037,'displacement_percent':4.3478261}]}}
    status={'state':'complete','cad_sha256':SHA,'run_id':R12ID,
            'candidate_count':1}
    return agent,status,raw_r12,raw_ml

class PaidEvidenceGate(unittest.TestCase):
    def test_reverified_allowlisted_json_has_all_five_sources(self):
        a,s,r,m=fixture()
        copy_before=copy.deepcopy((a,s,r,m))
        proof=check(a,UID,SHA,s,r,m)
        self.assertEqual((a,s,r,m),copy_before)
        self.assertEqual(proof['source'],
                         'independent_same_run_prepaid_server_verification')
        for key in ('cad_source_proof','brepmfr_research_proof',
                    'r12_research_proof','fea_3d_surface_proof','mesh_runs_verified'):
            self.assertIn(key,proof)
        self.assertEqual(proof['brepmfr_research_proof']['face_count'],2)
        self.assertEqual(proof['r12_research_proof']['candidate_count'],1)
        self.assertEqual(proof['fea_3d_surface_proof']['stress_peak']['unit'],'MPa')
        self.assertFalse(proof['fea_3d_surface_proof']['rendered_png_transmitted'])
        raw=json.dumps(proof)
        for sensitive in (UID,SHA,CASE,RUN,MLID,R12ID,'face_ordinal','face_index'):
            self.assertNotIn(sensitive,raw)
    def test_missing_or_contradictory_source_never_passes(self):
        mutations=[
          lambda a,s,r,m:a['cad_features'].update(cad_sha256='f'*64),
          lambda a,s,r,m:a['cad_features'].update(candidate_count=2),
          lambda a,s,r,m:a['hole_geometry_summary'].update(status='failed'),
          lambda a,s,r,m:a['ml'].update(status='not_run'),
          lambda a,s,r,m:a['ml'].update(candidate_count=99),
          lambda a,s,r,m:m['result'].update(sha256='f'*64),
          lambda a,s,r,m:m['result']['variants']['topology_trimmed']['faces'][0].update(
                 model_score_uncalibrated=1.1),
          lambda a,s,r,m:s.update(run_id='f'*32),
          lambda a,s,r,m:r['result']['predictions'][0].update(
                 predicted_hole_type='blind_hole'),
          lambda a,s,r,m:a['fea'].update(status='not_verified'),
          lambda a,s,r,m:a['fea'].update(maximum_von_mises_mpa=float('nan')),
          lambda a,s,r,m:a['fea_spatial'].update(run_id='f'*32),
          lambda a,s,r,m:a['fea_spatial']['stress_peak'].update(value=999),
          lambda a,s,r,m:a['fea_spatial']['displacement_peak'].update(unit='MPa'),
          lambda a,s,r,m:a['engineering_context'].update(applied_force_n=None),
          lambda a,s,r,m:a.update(mesh_followup_context=None),
          lambda a,s,r,m:a['mesh_followup_context'].update(status='running'),
          lambda a,s,r,m:a['mesh_followup_context']['runs_coarse_to_fine'][1].update(
                 target_mesh_mm=9),
          lambda a,s,r,m:a['mesh_followup_context']['adjacent_relative_change_percent'][0].update(
                 stress_percent=1.0),
          lambda a,s,r,m:a['mesh_followup_context']['adjacent_relative_change_percent'][1].update(
                 displacement_percent=0.0),
          lambda a,s,r,m:a['mesh_followup_context']['runs_coarse_to_fine'][2].update(
                 max_displacement_mm=0.0),
        ]
        for i,mutate in enumerate(mutations):
            with self.subTest(case=i):
                a,s,r,m=fixture()
                mutate(a,s,r,m)
                with self.assertRaises(ValueError):
                    check(a,UID,SHA,s,r,m)
    def test_paid_route_preflight_is_before_provider_call(self):
        start=TEXT.index("if path.startswith('/api/agent/evidence/'):")
        scope=TEXT[start:TEXT.index("if path.startswith('/api/",start+1)]
        self.assertLess(scope.index('gf_paid_ai_preflight('),
                        scope.index('gf_agent_llm_optional(response,opt_in=True)'))
        self.assertIn("if gf_agent_llm_config()['configured']:",scope)
        self.assertIn('latest_r12[-1] if latest_r12 else None,ml',scope)
        self.assertIn("response['paid_input_evidence']",scope)
        self.assertIn("for name in ('cad_source_proof','brepmfr_research_proof',",TEXT)
        self.assertIn("data[name]=paid_proof[name]",TEXT)

if __name__=='__main__':
    unittest.main()
