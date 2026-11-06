"""Stage 3 local-only handoff: production binder, real server route/source gates.

This checks existing agent integration without starting any actual paid provider,
solver, ML trainer, SQLite writer or user Windows application.
"""
import ast
import copy
import re
import unittest
from pathlib import Path

SERVER = (Path(__file__).resolve().parents[1] / 'payload/GeoField_CAD_Analysis.py').read_text(encoding='utf-8')
JS = (Path(__file__).resolve().parents[1] / 'payload/frontend/cad.js').read_text(encoding='utf-8')
UID = 'a' * 32
SHA = 'b' * 64
BREP_RUN = 'c' * 32
R12_RUN = 'd' * 32

node = next(n for n in ast.parse(SERVER).body if isinstance(n, ast.FunctionDef)
            and n.name == 'gf_agent_apply_ml_handoff')
namespace = {'valid_uid': lambda x: isinstance(x,str) and
             re.fullmatch(r'[0-9a-f]{32}',x) is not None}
exec(compile(ast.Module(body=[node], type_ignores=[]),
             '<production local ML -> agent binding>', 'exec'), namespace)
bind = namespace['gf_agent_apply_ml_handoff']


def agent():
    return {'schema':'geofield-evidence-agent-v1','mode':'rules_only',
            'cad_sha256':SHA,'cad':{'job_id':UID},
            'fea':{'status':'not_verified'},
            'llm':{'connected':False,'executed':False,'provider':None},
            'findings':[{'kind':'cad','title':'measured',
                         'evidence':'direct CAD','next_check':'measure'}]}


def handoff():
    models={
       'brepmfr':{'status':'research_output_verified','run_id':BREP_RUN,
                   'candidate_count':1,'research_only':True,'structural_authority':False},
       'r12':{'status':'research_output_verified','run_id':R12_RUN,
              'candidate_count':0,'research_only':True,'structural_authority':False}}
    resolved=[{'model':name,'kind':'runtime_output_verified',
               'run_id':v['run_id'],'candidate_count':v['candidate_count']}
              for name,v in models.items()]
    uncertain=[{'model':name,'kind':'research_predictions_only',
                'run_id':v['run_id'],'candidate_count':v['candidate_count'],
                'samples':[]}
               for name,v in models.items()]
    return {'schema':'geofield-ml-handoff-v1','cad_job_id':UID,'cad_sha256':SHA,
            'research_only':True,'structural_authority':False,
            'fea_calculated':False,'face_mapping_verified':False,
            'models':models,'resolved':resolved,'uncertain':uncertain,
            'failed':[],'unavailable':[],'pending':[]}


def ocp():
    return {'source':'local_ocp_solid_occupancy_not_ml','status':'complete',
            'through_cylindrical_face_count':4,'blind_cylindrical_face_count':0,
            'unverified_cylindrical_face_count':0,
            'unique_drilled_hole_count_verified':False,
            'mechanical_cause_verified':False}


class MlToLocalAgentIntegration(unittest.TestCase):
    def test_verified_runs_are_not_approved_geometry(self):
        raw=agent(); models=handoff()
        original=copy.deepcopy((raw,models))
        result=bind(raw,models,ocp())
        self.assertEqual((raw,models),original)
        self.assertEqual(result['ml_handoff']['schema'],'geofield-ml-handoff-v1')
        self.assertEqual(len(result['findings']),3)
        self.assertTrue(all(row['kind']=='ml' and row['level']=='research'
                            for row in result['findings'][1:]))
        self.assertTrue(all('정답 미확정' in row['title'] for row in result['findings'][1:]))
        self.assertEqual(result['ml_cad_crosscheck']['status'],
                         'independent_ocp_cylinders_available')
        self.assertEqual(result['ml_cad_crosscheck']['observed_cylindrical_faces']
                         ['through_cylindrical_face_count'],4)
        self.assertIs(result['ml_cad_crosscheck']['ml_to_cad_face_mapping_verified'],False)
        self.assertIs(result['ml_cad_crosscheck']['ml_geometry_classification_verified'],False)
        self.assertEqual(result['fea'],raw['fea'])
        self.assertEqual(result['llm'],raw['llm'])

    def test_failure_on_one_model_keeps_independent_valid_research(self):
        h=handoff()
        h['models']['brepmfr']={'status':'failed','run_id':None,
              'candidate_count':None,'research_only':True,'structural_authority':False}
        h['resolved']=[x for x in h['resolved'] if x['model']!='brepmfr']
        h['uncertain']=[x for x in h['uncertain'] if x['model']!='brepmfr']
        h['failed']=[{'model':'brepmfr','status':'failed'}]
        result=bind(agent(),h)
        self.assertEqual(result['findings'][1]['level'],'blocked')
        self.assertIn('R12',result['findings'][2]['title'])
        self.assertEqual(result['ml_cad_crosscheck']['status'],
                         'independent_cad_crosscheck_unavailable')

    def test_pending_or_off_models_are_never_promoted(self):
        h=handoff()
        h['models']['r12']={'status':'pending','run_id':None,'candidate_count':None,
            'research_only':True,'structural_authority':False}
        h['resolved']=[x for x in h['resolved'] if x['model']!='r12']
        h['uncertain']=[x for x in h['uncertain'] if x['model']!='r12']
        h['pending']=[{'model':'r12','status':'pending'}]
        res=bind(agent(),h)
        self.assertIn('pending',res['findings'][2]['title'])

    def test_mismatched_sha_or_identity_fails_closed(self):
        for change in (
            lambda x:x.update(cad_sha256='f'*64),
            lambda x:x.update(cad_job_id='f'*32),
            lambda x:x.update(structural_authority=True),
            lambda x:x.update(face_mapping_verified=True),
            lambda x:x.update(fea_calculated=True),
            lambda x:x.update(research_only=False),
            lambda x:x.update(schema='corrupt'),
        ):
            h=handoff();change(h)
            with self.assertRaises(ValueError):
                bind(agent(),h)

    def test_forged_or_partial_predictions_cannot_be_verified(self):
        for change in (
            lambda x:x['models']['r12'].update(candidate_count=100),
            lambda x:x['models']['brepmfr'].update(run_id='z'*32),
            lambda x:x['uncertain'][0].update(run_id='e'*32),
            lambda x:x['resolved'][0].update(candidate_count=99),
            lambda x:x['resolved'].pop(),
            lambda x:x['uncertain'].pop(),
            lambda x:x['models']['r12'].update(structural_authority=True),
            lambda x:x['models'].update(fake={'status':'research_output_verified'}),
            lambda x:x['failed'].append({'model':'unknown','status':'failed'}),
        ):
            h=handoff();change(h)
            with self.assertRaises(ValueError):
                bind(agent(),h)

    def test_untrusted_ocp_does_not_create_false_measured_cad_facts(self):
        for change in (
            lambda x:x.update(unique_drilled_hole_count_verified=True),
            lambda x:x.update(source='from_ml'),
            lambda x:x.update(through_cylindrical_face_count=200),
            lambda x:x.update(mechanical_cause_verified=True)
        ):
            e=ocp();change(e)
            result=bind(agent(),handoff(),e)
            self.assertNotIn('observed_cylindrical_faces',result['ml_cad_crosscheck'])
            self.assertEqual(result['ml_cad_crosscheck']['status'],
                             'independent_cad_crosscheck_unavailable')

    def test_route_uses_existing_validators_and_prevents_stale_handoff(self):
        route=SERVER[SERVER.index("if path.startswith('/api/agent/evidence/'):"):
                     SERVER.index("if path.startswith('/api/integration/decision/'):")]
        self.assertIn('r12_candidates=[dict(v) for v in R12_JOBS.values()',route)
        self.assertIn('gf_ml_handoff_snapshot(uid,sha,job,ml,',route)
        self.assertIn('response=gf_agent_apply_ml_handoff(response,handoff,',route)
        self.assertLess(route.index('response=gf_agent_evaluate('),
                        route.index('response=gf_agent_apply_ml_handoff('))
        self.assertLess(route.index('response=gf_agent_apply_ml_handoff('),
                        route.index("query=urllib.parse.parse_qs("))
        self.assertIn("self.headers.get('X-GeoField-LLM-Opt-In')=='1'",route)
        self.assertLess(route.index('gf_paid_ai_preflight('),
                        route.index('gf_agent_llm_optional(response,opt_in=True)'))
        self.assertIn('latest_ml=[v.get(\'id\') for v in ML_JOBS.values()',route)
        self.assertIn('r12_at_end=r128_r12_status(uid,sha)',route)

    def test_background_local_analysis_has_no_tab_dependency_or_paid_optin(self):
        start=JS.index('function gfMaybeAutoAnalyze(){')
        end=JS.index('// Read-only evidence-based agent;',start)
        auto=JS[start:end]
        self.assertNotIn("active!=='integration'",auto)
        self.assertIn("btn.dataset.gfAutoLocalOnly='1'",auto)
        self.assertIn('btn.onclick()',auto)
        updated=JS[JS.index('function gfResearchEvidenceUpdated('):start]
        self.assertNotIn("active==='integration'",updated)
        handler=JS[JS.index("$('agentRunBtn').onclick=async()=>{"):
                   JS.index("$('reviewBtn').onclick=async()=>{")]
        self.assertIn('const externalOptIn=!automaticLocal&&',handler)
        self.assertIn("const handoff=data.ml_handoff;",handler)
        self.assertIn('contrast.ml_to_cad_face_mapping_verified!==false',handler)
        self.assertIn("if(automaticLocal&&researchRevisionAtStart!==gfResearchEvidenceRevision)",handler)
        self.assertNotIn('if(automaticLocal&&active===',handler)
        self.assertIn('gfResearchEvidenceUpdated(cadId,expectedSha);',JS)

    def test_pure_function_no_paid_solver_disk_or_new_model(self):
        source=ast.get_source_segment(SERVER,node)
        for forbidden in ('gf_agent_llm_optional(', 'subprocess.', 'requests.',
                          'sqlite3.', 'launch_automatic_ml(', 'launch_automatic_r12(',
                          'execute_fea(', 'file_path.write', 'open('):
            self.assertNotIn(forbidden,source)


if __name__ == '__main__':
    unittest.main()
