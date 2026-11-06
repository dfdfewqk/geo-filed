"""Stage 5: original local AI report + immutable paid input source gate.

Tests AST-extracted production functions, using only isolated synthetic data.
No external HTTP, model charge, local user STEP, FEA solve or SQLite write.
"""
import ast
import copy
import re
import threading
import unittest
from pathlib import Path

SOURCE=(Path(__file__).resolve().parents[1]/'payload/GeoField_CAD_Analysis.py').read_text(encoding='utf8')
TREE=ast.parse(SOURCE)
JOB='a'*32
CAD='b'*64
CASE='c'*64
BASE='d'*32
STUDY='e'*32

def extract(names, env):
    funcs=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if {n.name for n in funcs}!=set(names):
        raise AssertionError('Missing production local/paid integration functions')
    ns=dict(env)
    exec(compile(ast.Module(body=funcs,type_ignores=[]),'<stage5-production>','exec'),ns)
    return ns

valid=lambda x:isinstance(x,str) and re.fullmatch('[0-9a-f]{32}',x) is not None

def study_data():
    return {'id':STUDY,'cad_job_id':JOB,'cad_sha256':CAD,'status':'complete',
            'base_run_id':BASE,'base_case_sha256':CASE,
            'analysis_snapshot_ids':['1'*32,'2'*32,'3'*32],
            # Successful studies intentionally release all 3 temp cases.
            'mesh_study_verified':False}

def analysis():
    return {'status':'verified_three_mesh_sensitivity_only',
            'same_physical_case':True,
            'solver_evidence':'each_calculix_run_revalidated',
            'convergence_certified':False,'safety_certified':False,
            'runs_coarse_to_fine':[
                {'cad_sha256':CAD,'mesh_target_mm':3.,
                 'max_stress_mpa':13.,'max_displacement_mm':.02},
                {'cad_sha256':CAD,'mesh_target_mm':2.,
                 'max_stress_mpa':14.,'max_displacement_mm':.022},
                {'cad_sha256':CAD,'mesh_target_mm':1.5,
                 'max_stress_mpa':14.5,'max_displacement_mm':.023}],
            'adjacent_changes':[
                {'stress_relative_change_percent':7.142857,
                 'displacement_relative_change_percent':9.090909},
                {'stress_relative_change_percent':3.448276,
                 'displacement_relative_change_percent':4.347826}],
            'actual_load_moment_diagnostic':{'mesh_only_attribution_supported_by_this_screen':True},
            'numeric_stability_diagnostic':{'passes':True},
            'actual_mesh_resolution_diagnostic':{'effective_mean_edge_refinement':True}}

class Stage5Tests(unittest.TestCase):
    def mesh_env(self):
        mem=study_data()
        seen=[]
        def verify(study):
            seen.append(('reverify_three_solver_archives',study['id']))
            return {'id':STUDY,'status':'complete','mesh_study_verified':True,
                    'base_fea_binding_verified':True,'base_run_id':BASE,
                    'base_case_sha256':CASE,'study_analysis':analysis()}
        ns=extract({'gf_ai_verified_mesh_followup'},
                   {'valid_uid':valid,'STATE_LOCK':threading.RLock(),
                    'MESH_STUDIES':{STUDY:mem},
                    'r1213_mesh_series_verified_public':verify})
        return ns,mem,seen

    def test_paid_followup_uses_verified_archives_after_temp_cases_removed(self):
        ns,mem,seen=self.mesh_env()
        prior=copy.deepcopy(mem)
        proof=ns['gf_ai_verified_mesh_followup'](
            STUDY,JOB,CAD,{'cad_sha256':CAD,'case_sha256':CASE},BASE)
        self.assertIsNotNone(proof)
        self.assertEqual(len(proof['runs_coarse_to_fine']),3)
        self.assertEqual(proof['source'],'three_independently_reverified_calculix_runs')
        self.assertEqual(seen,[('reverify_three_solver_archives',STUDY)])
        self.assertEqual(mem,prior)
        self.assertNotIn('cases',mem)
        self.assertFalse(proof['convergence_certified'])
        self.assertFalse(proof['safety_certified'])

    def test_paid_followup_rejects_stale_run_or_old_unsigned_manifest(self):
        ns,mem,seen=self.mesh_env()
        fn=ns['gf_ai_verified_mesh_followup']
        case={'cad_sha256':CAD,'case_sha256':CASE}
        for old in (None,'f'*32,'bad'):
            self.assertIsNone(fn(STUDY,JOB,CAD,case,old))
        self.assertIsNone(fn(STUDY,JOB,CAD,{**case,'case_sha256':'f'*64},BASE))
        self.assertEqual(seen,[])
        mem['base_run_id']='f'*32
        self.assertIsNone(fn(STUDY,JOB,CAD,case,BASE))
        mem['base_run_id']=BASE
        del mem['base_case_sha256']
        self.assertIsNone(fn(STUDY,JOB,CAD,case,BASE))
        self.assertEqual(seen,[])

    def test_paid_followup_rejects_unreverified_base_run_even_with_3_green_runs(self):
        ns,mem,seen=self.mesh_env()
        ns['r1213_mesh_series_verified_public']=lambda study:{
            'id':STUDY,'status':'complete','mesh_study_verified':True,
            'base_fea_binding_verified':False,'base_run_id':BASE,
            'base_case_sha256':CASE,'study_analysis':analysis()}
        self.assertIsNone(ns['gf_ai_verified_mesh_followup'](
            STUDY,JOB,CAD,{'cad_sha256':CAD,'case_sha256':CASE},BASE))

    def test_real_https_requires_prepaid_source_proof_no_transport(self):
        env={'GEOFIELD_AGENT_LLM_ENABLED':'1',
             'GEOFIELD_AGENT_LLM_PROVIDER':'openai',
             'GEOFIELD_AGENT_LLM_MODEL':'test-model',
             'GEOFIELD_AGENT_LLM_API_KEY':'TEST-FAKE-KEY-NO-NETWORK'}
        ns=extract({'gf_agent_llm_config','gf_agent_llm_optional'}, {})
        basic={'schema':'geofield-evidence-agent-v1','cad_sha256':CAD,
               'fea':{'status':'INP_STA_FRD_reverified','run_id':BASE,
                      'case_sha256':CASE}}
        for proof in (None,{}, {'source':'forged'},
                      {'source':'independent_same_run_prepaid_server_verification',
                       'mesh_runs_verified':2}):
            agent={**basic,'paid_input_evidence':proof}
            result=ns['gf_agent_llm_optional'](agent,opt_in=True,environ=env)
            self.assertEqual(result['status'],'invalid_evidence')
            self.assertFalse(result['executed'])
        self.assertEqual(ns['gf_agent_llm_optional'](
            basic,opt_in=False,environ=env)['status'],'rules_only')

    def test_rule_agent_report_reuses_stage3_source_handoff_without_credits(self):
        checked=[]
        def evaluator(summary,decision,ml,r12,fea,**kwargs):
            checked.append('evaluate')
            return {'schema':'geofield-evidence-agent-v1','mode':'rules_only',
                    'cad_sha256':CAD,'cad':{'job_id':JOB},
                    'llm':{'connected':False,'executed':False,'provider':None},
                    'persisted_report':False,'fea':{'status':'not_verified'},
                    'findings':[{'kind':'cad','title':'STEP 측정',
                                 'evidence':'current original',
                                 'next_check':'compare CAD'}]}
        ns=extract({'gf_current_report_agent','gf_agent_apply_ml_handoff',
                    'gf_ml_handoff_snapshot','gf_render_live_agent_report'},{
            'STATE_LOCK':threading.RLock(),'CURRENT':{'job_id':JOB},
            'JOBS':{JOB:{'status':'complete','sha256':CAD}},
            'ML_JOBS':{},'R12_JOBS':{},'valid_uid':valid,
            'review_decision':lambda *args:{'cad_sha256':CAD,'items':[]},
            'gf_agent_cad_features':lambda *args:{'candidates':[]},
            'gf_agent_evaluate':evaluator,
            'r128_r12_status':lambda *args:{'state':'not_run'},
            'gf_verified_hole_summary':lambda *args:None,
            'gf_agent_restored_context':lambda *args:{'status':'not_restored'},
            'qa_current_cad_evidence':lambda *args:True,
            'gf_agent_assert_restore_session':lambda *args:True})
        job={'id':JOB,'status':'complete','sha256':CAD,'analysis':{},
             'findings':[],'auto_ml_enabled':True,
             'auto_ml_status':'pending','auto_r12_status':'not_run'}
        summary={'cad':{'sha256':CAD},'fea_case_provenance':{}}
        agent=ns['gf_current_report_agent'](
            summary,JOB,job,{'mesh':{'face_ids':[]}},
            None,None,None,None,{'job_id':JOB})
        self.assertEqual(checked,['evaluate'])
        self.assertEqual(agent['ml_handoff']['cad_sha256'],CAD)
        self.assertEqual(len(agent['ml_handoff']['pending']),2)
        self.assertEqual(len(agent['findings']),3)
        self.assertFalse(agent['ml_cad_crosscheck']['structural_safety_verified'])
        self.assertFalse(agent['llm']['executed'])
        html=ns['gf_render_live_agent_report'](
            '<html><body><h1>Measured FEA</h1></body></html>',summary,agent)
        self.assertIn('BrepMFR',html)
        self.assertIn('R12',html)
        self.assertIn('Measured FEA',html)

    def test_source_and_ui_paid_path_remain_explicit_one_shot(self):
        ui=(Path(__file__).resolve().parents[1]/'payload/frontend/cad.js').read_text(encoding='utf8')
        beg=SOURCE.index("if path.startswith('/api/agent/evidence/'):")
        route=SOURCE[beg:SOURCE.index("if path.startswith('/api/integration/decision/'):",beg)]
        self.assertIn("self.headers.get('X-GeoField-LLM-Opt-In')=='1'",route)
        self.assertIn("query.get('llm')==['1']",route)
        self.assertIn("site in (None,'none','same-origin')",route)
        self.assertLess(route.index('gf_paid_ai_preflight('),
                        route.index('gf_agent_llm_optional(response,opt_in=True)'))
        self.assertIn("if gf_agent_llm_config()['configured']:",route)
        self.assertIn("if(toggle)toggle.checked=false;",ui)
        self.assertIn("const externalOptIn=!automaticLocal&&",ui)
        self.assertIn("btn.dataset.gfAutoLocalOnly='1'",ui)
        self.assertIn("if(!includeExternal){",ui)
        self.assertIn("gfRequireCompletePaidReportEvidence(",ui)
        self.assertIn("(response.get('fea') or {}).get('run_id')",route)

if __name__=='__main__':
    unittest.main()
