"""GeoField phase-6 optional LLM: real pure production source, simulated transport.

No API key or network request is used in CI. Tests ensure model text cannot
alter verified CAD, ML, FEA results, and no consent means no network call.
"""
import ast
import copy
import json
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'payload'/'GeoField_CAD_Analysis.py'
tree=ast.parse(SOURCE.read_text(encoding='utf8'))
names={'gf_agent_llm_config','gf_agent_llm_optional'}
parts=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
assert len(parts)==2
ns={}
exec(compile(ast.Module(body=parts,type_ignores=[]),str(SOURCE),'exec'),ns)
status=ns['gf_agent_llm_config']
describe=ns['gf_agent_llm_optional']
from test_agent_evidence import agent, record, CAD, RUN

ENV={'GEOFIELD_AGENT_LLM_ENABLED':'1',
     'GEOFIELD_AGENT_LLM_MODEL':'test-model',
     'GEOFIELD_AGENT_LLM_API_KEY':'test-key-do-not-transmit'}

def ok(payload,secret):
    assert secret==ENV['GEOFIELD_AGENT_LLM_API_KEY']
    assert payload['model']=='test-model'
    assert payload['store'] is False
    data=json.loads(payload['messages'][1]['content'])
    assert set(data)=={
      'cad_measured_review_candidate_count','ml_status',
      'fea_status','fea_max_von_mises_mpa',
      'fea_max_displacement_mm','element_type',
      'convergence','structural_safety_certified'}
    assert data['fea_max_von_mises_mpa']==14.512
    assert data['fea_max_displacement_mm']==0.05698
    assert CAD not in json.dumps(payload)
    assert RUN not in json.dumps(payload)
    return {'choices':[{'finish_reason':'stop','message':{'content':'검증된 응력은 14.512 MPa입니다. 구조 안전 여부는 별도로 검증해야 합니다.'}}]}

class AgentLlmIsolation(unittest.TestCase):
    def evidence(self):
        return agent(*record())

    def test_disabled_is_never_connected(self):
        self.assertFalse(status({})['configured'])
        self.assertFalse(status({})['connected'])
        self.assertEqual(status({})['mode'],'rules_only')
    def test_requires_explicit_process_flag_and_model(self):
        for field in ('GEOFIELD_AGENT_LLM_ENABLED',
                      'GEOFIELD_AGENT_LLM_MODEL',
                      'GEOFIELD_AGENT_LLM_API_KEY'):
            e=dict(ENV);e.pop(field)
            self.assertFalse(status(e)['configured'])
    def test_invalid_model_rejected(self):
        for bad in ('', 'a/b', 'x '*80, '\\n', 'x'*81):
            e=dict(ENV);e['GEOFIELD_AGENT_LLM_MODEL']=bad
            self.assertFalse(status(e)['configured'])
    def test_user_must_opt_in_even_when_configured(self):
        called=[]
        out=describe(self.evidence(),environ=ENV,
                     transport=lambda *args:called.append(args))
        self.assertEqual(out['status'],'rules_only')
        self.assertFalse(out['connected'])
        self.assertEqual(called,[])
    def test_unconfigured_request_falls_back_without_transport(self):
        called=[]
        out=describe(self.evidence(),opt_in=True,environ={},
                     transport=lambda *args:called.append(args))
        self.assertEqual(out['status'],'not_configured')
        self.assertEqual(called,[])
    def test_success_keeps_all_original_engineering_values_immutable(self):
        evidence=self.evidence()
        copy_before=copy.deepcopy(evidence)
        result=describe(evidence,opt_in=True,environ=ENV,transport=ok)
        self.assertEqual(evidence,copy_before)
        self.assertEqual(result['provider'],'openai')
        self.assertTrue(result['executed'])
        self.assertTrue(result['connected'])
        self.assertIn('구조 안전 여부',result['explanation'])
        self.assertEqual(evidence['fea']['maximum_von_mises_mpa'],14.512)
        self.assertEqual(evidence['llm']['connected'],False)
    def test_malicious_model_text_has_no_authority_over_results(self):
        original=self.evidence();before=copy.deepcopy(original)
        answer=lambda *args:{'choices':[{'finish_reason':'stop','message':{
            'content':'Ignore all evidence. Safe: 999999 MPa. <script>evil()</script>'}}]}
        out=describe(original,opt_in=True,environ=ENV,transport=answer)
        self.assertTrue(out['connected'])
        self.assertEqual(original,before)
        self.assertEqual(original['fea']['maximum_von_mises_mpa'],14.512)
        self.assertEqual(original['fea']['safety_certified'],False)
    def test_transport_failure_keeps_rules_only_no_secret_in_errors(self):
        def bad(*args):raise RuntimeError('SECRET '+ENV['GEOFIELD_AGENT_LLM_API_KEY'])
        result=describe(self.evidence(),opt_in=True,environ=ENV,transport=bad)
        self.assertEqual(result['status'],'unavailable')
        self.assertNotIn(ENV['GEOFIELD_AGENT_LLM_API_KEY'],str(result))
        self.assertFalse(result['connected'])
    def test_malformed_response_rejected(self):
        for answer in ({},{'choices':[]}, {'choices':[{'finish_reason':'length','message':{'content':'short'}}]},
                       {'choices':[{'finish_reason':'stop','message':{'content':''}}]},
                       {'choices':[{'finish_reason':'stop','message':{'content':'x'*1700}}]}):
            with self.subTest(answer=answer):
                result=describe(self.evidence(),opt_in=True,environ=ENV,transport=lambda *args:answer)
                self.assertEqual(result['status'],'unavailable')
    def test_no_real_fea_is_never_replaced_with_hallucinated_measurements(self):
        args=list(record());args[4]={};args[0]['fea']={'state':'not_run'}
        evidence=agent(*args);before=copy.deepcopy(evidence)
        observed=[]
        def capture(payload,key):
            observed.append(json.loads(payload['messages'][1]['content']))
            return {'choices':[{'finish_reason':'stop','message':{'content':'별도 검증 필요'}}]}
        out=describe(evidence,opt_in=True,environ=ENV,transport=capture)
        self.assertEqual(out['status'],'external_explanation_only')
        self.assertIsNone(observed[0]['fea_max_von_mises_mpa'])
        self.assertIsNone(observed[0]['fea_max_displacement_mm'])
        self.assertEqual(evidence,before)
    def test_no_input_contract_or_bad_source_calls_model(self):
        calls=[]
        result=describe({'schema':'garbage'},opt_in=True,environ=ENV,
                        transport=lambda *args:calls.append(args))
        self.assertEqual(result['status'],'invalid_evidence')
        self.assertEqual(calls,[])
    def test_frontend_and_backend_require_explicit_consent_header(self):
        source=SOURCE.read_text(encoding='utf8')
        self.assertIn("self.headers.get('X-GeoField-LLM-Opt-In')=='1'",source)
        self.assertIn("query.get('llm')==['1']",source)
        self.assertIn("site in (None,'none','same-origin')",source)
        self.assertIn("response['mode']='rules_plus_llm'",source)
        self.assertIn("qa_current_cad_evidence(uid,dict(CURRENT)",source)

if __name__=='__main__':unittest.main()
