"""Active CAD geometry and face-map integrity against the production check.

The inputs are synthetic CAD job metadata, not actual STEP measurements.
"""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'payload'/'GeoField_CAD_Analysis.py').read_text(encoding='utf-8')
TREE=ast.parse(SOURCE)
nodes=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='qa_current_cad_evidence']
assert len(nodes)==1
scope={'valid_uid':lambda x:isinstance(x,str) and len(x)==32 and
       all(c in '0123456789abcdef' for c in x)}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'geofield_cad_verifier','exec'),scope)
check=scope['qa_current_cad_evidence']
OLD='1'*32
NEW='2'*32
SHA='a'*64
def fresh():
    session={'job_id':OLD,'pending_job_id':OLD}
    job={'id':OLD,'status':'complete','sha256':SHA,'analysis':{'sha256':SHA}}
    model={'sha256':SHA,'mesh':{'face_ids':[6,7,11,12]}}
    return session,job,model

class VerifiedCadEvidenceTests(unittest.TestCase):
    def test_valid_active_cad_and_face_map(self):
        session,job,model=fresh()
        self.assertEqual(check(OLD,session,job,model),SHA)
    def test_restored_cad_without_pending_import_is_valid(self):
        session,job,model=fresh()
        session.pop('pending_job_id')
        self.assertEqual(check(OLD,session,job,model),SHA)
    def test_new_pending_step_blocks_old_data(self):
        session,job,model=fresh()
        session.update(job_id=None,pending_job_id=NEW)
        with self.assertRaises(ValueError):check(OLD,session,job,model)
    def test_new_step_completed_rejects_old_data(self):
        session,job,model=fresh()
        session.update(job_id=NEW,pending_job_id=NEW)
        with self.assertRaises(ValueError):check(OLD,session,job,model)
    def test_conflicting_pending_step_rejects_even_if_old_cad_active(self):
        session,job,model=fresh()
        session['pending_job_id']=NEW
        with self.assertRaises(ValueError):check(OLD,session,job,model)
    def test_mismatched_job_identity_or_unfinished_job(self):
        for key,value in [('id',NEW),('status','running')]:
            session,job,model=fresh()
            job[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):check(OLD,session,job,model)
    def test_wrong_cad_analysis_sha_and_mesh_sha(self):
        for kind in ('analysis','mesh'):
            session,job,model=fresh()
            if kind=='analysis':job['analysis']['sha256']='b'*64
            else:model['sha256']='b'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):check(OLD,session,job,model)
    def test_absent_or_invalid_face_mapping(self):
        for value in (None,[],{'id':6}):
            session,job,model=fresh()
            model['mesh']['face_ids']=value
            if isinstance(value,list):
                self.assertEqual(check(OLD,session,job,model),SHA)
            else:
                with self.assertRaises(ValueError):check(OLD,session,job,model)
    def test_api_routes_recheck_active_cad_after_slow_analysis(self):
        for start,end in (
            ("if path.startswith('/api/geometry/dimensions/'):","if path.startswith('/api/results/summary/')"),
            ("if path.startswith('/api/integration/decision/'):","if path.startswith('/api/jobs/')"),
        ):
            block=SOURCE[SOURCE.index(start):SOURCE.index(end,SOURCE.index(start))]
            self.assertIn('qa_current_cad_evidence(uid,dict(CURRENT),dict(JOBS.get(uid) or {})',block)
            self.assertIn("return self.send_raw(",block)

if __name__=='__main__':
    unittest.main()
