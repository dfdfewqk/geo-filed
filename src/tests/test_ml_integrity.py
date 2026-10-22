"""ML trust-boundary tests against extracted production functions.

Synthetic worker JSON only: never represent these as genuine model inference.
No proprietary STEP, user history or checkpoint modifications.
"""
import ast
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BRIDGE=ROOT/'payload'/'ml_r12_bridge.py'
SERVER=ROOT/'payload'/'GeoField_CAD_Analysis.py'

def extract(path,functions,globals_):
    ast_tree=ast.parse(path.read_text(encoding='utf8'))
    picked=[n for n in ast_tree.body if isinstance(n,ast.FunctionDef) and n.name in functions]
    assert len(picked)==len(functions), f'function missing: {functions}'
    exec(compile(ast.Module(body=picked,type_ignores=[]),str(path),'exec'),globals_)
    return globals_

bridge=extract(BRIDGE,{'validate_research_result'},{'math':math})
backend=extract(SERVER,{'qa_validate_brepmfr_diagnostic'},{})

SHA='a'*64
def valid_r12():
    return {
      'cad_sha256':SHA,'decision_usage':'blocked_diagnostic_only',
      'status':'research_not_for_production','fea_calculated':False,
      'geometry_certified':False,'is_independent_r12_research':True,
      'candidate_count':1,'predictions':[{
        'face_index':6,'uncalibrated_model_score':0.83,
        'raw_ml_top_class':'through_hole','raw_ml_thresholded':'unverified',
        'predicted_hole_type':'through_hole','topology_evidence':'through_hole',
        'decision_basis':'model_and_brep_topology_agree','status':'research_unverified'
      }]
    }
def valid_brep():
    return {'sha256':SHA,'decision_usage':'blocked_diagnostic_only',
      'variants':{'topology_trimmed':{'faces':[{
        'face_ordinal':1,'geometry_surface':'CYLINDER',
        'model_class':'diagnostic_face','model_score_uncalibrated':0.45
      }]}}}

class R12Contract(unittest.TestCase):
    def check(self,d):
        return bridge['validate_research_result'](d,SHA)
    def test_consistent_research_candidate(self):
        d=valid_r12();self.assertIs(self.check(d),d)
    def test_empty_research_result_is_permitted(self):
        d=valid_r12();d['candidate_count']=0;d['predictions']=[]
        self.assertIs(self.check(d),d)
    def test_wrong_sha_and_wrong_mode(self):
        for key,value in [('cad_sha256','b'*64),('decision_usage','production'),
                          ('fea_calculated',True),('geometry_certified',True),
                          ('is_independent_r12_research',False)]:
            d=valid_r12();d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(d)
    def test_candidate_count_mismatch_and_duplicates(self):
        for change in ('mismatch','duplicate'):
            d=valid_r12()
            if change=='mismatch':d['candidate_count']=2
            else:d['candidate_count']=2;d['predictions'].append(dict(d['predictions'][0]))
            with self.subTest(change=change),self.assertRaises(ValueError):self.check(d)
    def test_nonfinite_or_invalid_scores(self):
        for score in [float('nan'),float('inf'),-0.1,1.1,'0.9']:
            d=valid_r12();d['predictions'][0]['uncalibrated_model_score']=score
            with self.subTest(score=score),self.assertRaises(ValueError):self.check(d)
    def test_mismatched_model_and_topology_cannot_claim_accepted_hole(self):
        d=valid_r12();d['predictions'][0]['topology_evidence']='blind_hole'
        with self.assertRaisesRegex(ValueError,'모순'):self.check(d)
    def test_no_geometry_evidence_cannot_claim_confirmed_hole(self):
        d=valid_r12();x=d['predictions'][0]
        x['decision_basis']='insufficient_brep_evidence';x['topology_evidence']=None
        with self.assertRaisesRegex(ValueError,'모순'):self.check(d)
    def test_conflict_must_abstain(self):
        d=valid_r12();x=d['predictions'][0]
        x['decision_basis']='model_topology_conflict';x['topology_evidence']='blind_hole'
        with self.assertRaisesRegex(ValueError,'모순'):self.check(d)
        x['predicted_hole_type']='unverified'
        self.assertIs(self.check(d),d)
    def test_multisegment_must_abstain(self):
        d=valid_r12();d['predictions'][0]['decision_basis']='coaxial_multisegment_hole_unsupported'
        with self.assertRaises(ValueError):self.check(d)
    def test_bad_worker_status_and_face_ordinal(self):
        for key,value in [('status','verified'),('face_index',-2)]:
            d=valid_r12();d['predictions'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(d)

class BrepContract(unittest.TestCase):
    def check(self,d):
        return backend['qa_validate_brepmfr_diagnostic'](d,SHA)
    def test_valid_diagnostic_keeps_original_payload(self):
        d=valid_brep();raw=json.dumps(d,sort_keys=True)
        self.assertIs(self.check(d),d)
        self.assertEqual(json.dumps(d,sort_keys=True),raw)
    def test_empty_faces_is_valid_not_a_classification(self):
        d=valid_brep();d['variants']['topology_trimmed']['faces']=[]
        self.assertIs(self.check(d),d)
    def test_missing_faces_rejected(self):
        for value in [None,{}, {'variants':{}}]:
            with self.subTest(value=value),self.assertRaises(ValueError):self.check(value)
    def test_malicious_mode_or_cad_sha_rejected(self):
        for key,value in [('sha256','0'*64),('decision_usage','production')]:
            d=valid_brep();d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(d)
    def test_nonfinite_and_wrong_type_scores(self):
        for value in [float('inf'),float('nan'),None,'0.2']:
            d=valid_brep();d['variants']['topology_trimmed']['faces'][0]['model_score_uncalibrated']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.check(d)
    def test_duplicate_or_malformed_face_ordinal(self):
        d=valid_brep();d['variants']['topology_trimmed']['faces'].append(dict(d['variants']['topology_trimmed']['faces'][0]))
        with self.assertRaises(ValueError):self.check(d)
        d=valid_brep();d['variants']['topology_trimmed']['faces'][0]['face_ordinal']=True
        with self.assertRaises(ValueError):self.check(d)

class ModelAssetChecks(unittest.TestCase):
    def test_r12_weight_checksum_matches_verified_report(self):
        directory=ROOT/'payload'/'ml'/'r12_research'
        report=json.loads((directory/'report.json').read_text(encoding='utf-8'))
        actual=hashlib.sha256((directory/'research_model.joblib').read_bytes()).hexdigest()
        expected='df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0'
        self.assertEqual(actual,expected)
        self.assertEqual(report['model_sha256'],expected)
        self.assertEqual(report['eligible_for_production'],False)
        self.assertEqual(report['model_use'],'research_only')

    def test_feature_order_matches_frozen_training_report(self):
        directory=ROOT/'payload'/'ml'/'r12_research'
        source=ast.parse((directory/'features.py').read_text(encoding='utf-8'))
        constants=[node.value for node in source.body if isinstance(node,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='FEATURE_NAMES' for t in node.targets)]
        self.assertEqual(len(constants),1)
        names=ast.literal_eval(constants[0])
        report=json.loads((directory/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(names),10)
        self.assertEqual(names,report['feature_names'])


class WireChecks(unittest.TestCase):
    def test_r12_bridge_uses_validator_and_input_sha_twice(self):
        source=BRIDGE.read_text(encoding='utf8')
        start=source.index('def execute(root,step,out_dir):')
        block=source[start:]
        self.assertIn('return validate_research_result(d,expected_step_sha)',block)
        self.assertIn('expected_step_sha=sha(step)',block)
        self.assertIn('if sha(step)!=expected_step_sha:',block)
    def test_brepmfr_worker_requires_checkpoint_unchanged(self):
        source=SERVER.read_text(encoding='utf8')
        start=source.index('def execute_ml(');end=source.index('def launch_automatic_ml(',start)
        block=source[start:end]
        self.assertIn('file_sha256(checkpoint)!=BREPMFR_SHA256',block)
        self.assertIn('qa_validate_brepmfr_diagnostic(',block)

if __name__=='__main__':unittest.main()
