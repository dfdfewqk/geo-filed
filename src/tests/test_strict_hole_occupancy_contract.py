"""Regression contracts for independent B-Rep through/blind evidence.

CI uses synthetic JSON and AST only: no private STEP/weights/installed engines.
Real STEP occupancy was separately exercised with OCP in an isolated workspace.
"""
import ast
from pathlib import Path
import unittest

BACKEND=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(BACKEND.read_text(encoding="utf-8"))
FUNCTIONS={x.name:x for x in TREE.body if isinstance(x,ast.FunctionDef)}
SHA='a'*64

def sample():
    return {
        'schema':'geofield-hole-occupancy-v1',
        'source':'local_ocp_solid_occupancy_not_ml',
        'sha256':SHA,'viewer_face_mapping_verified':False,
        'decision_usage':'cad_diagnostic_only_not_fea_or_safety',
        'status':'complete','faces':[
          {'face_ordinal':1,'state':'through_hole','radius_mm':2.75,
           'axial_height_mm':3.,'end_states':['OUT','OUT']},
          {'face_ordinal':2,'state':'blind_hole','radius_mm':2.5,
           'axial_height_mm':8.,'end_states':['OUT','IN']},
          {'face_ordinal':3,'state':'unverified','reason':'ambiguous_or_stepped_exit'}]}

class HoleEvidenceGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        local={}
        assert 'qa_strict_hole_evidence' in FUNCTIONS
        exec(compile(ast.Module(body=[FUNCTIONS['qa_strict_hole_evidence']],
                                type_ignores=[]),str(BACKEND),'exec'),local)
        cls.validator=staticmethod(local['qa_strict_hole_evidence'])

    def test_accept_only_explicit_geometry_provenance(self):
        original=sample()
        self.assertIs(self.validator(original,SHA),original)

    def test_refuse_cross_cad_or_claimed_ml(self):
        variants=[
            ('sha256','b'*64),('source','brepmfr_epoch43'),
            ('schema','guess-v1'),('decision_usage','can_override_fea'),
            ('viewer_face_mapping_verified',True),
            ('viewer_face_mapping_verified','yes'),('status','published')]
        for field,value in variants:
            with self.subTest(field=field,value=value):
                d=sample();d[field]=value
                with self.assertRaises(ValueError):self.validator(d,SHA)

    def test_abstention_and_no_holes_are_valid(self):
        d=sample();d['faces']=[]
        self.assertIs(self.validator(d,SHA),d)
        d['status']='unverified'
        self.assertIs(self.validator(d,SHA),d)

    def test_invalid_face_ordinals_and_states_rejected(self):
        for value in [-1,0,513,True,'2']:
            with self.subTest(n=value):
                d=sample();d['faces'][1]['face_ordinal']=value
                with self.assertRaises(ValueError):self.validator(d,SHA)
        for value in ['certified','hole','through_hole_ml',True]:
            with self.subTest(state=value):
                d=sample();d['faces'][1]['state']=value
                with self.assertRaises(ValueError):self.validator(d,SHA)
        d=sample();d['faces'][1]['face_ordinal']=1
        with self.assertRaises(ValueError):self.validator(d,SHA)

    def test_bad_geometry_dimensions_rejected(self):
        for value in [-.1,0.,float('nan'),float('inf'),True,'3.0']:
            with self.subTest(value=value):
                d=sample();d['faces'][0]['radius_mm']=value
                with self.assertRaises(ValueError):self.validator(d,SHA)

    def test_step_only_used_before_disposable_copy_removed(self):
        assert 'strict_brep_hole_evidence' in FUNCTIONS
        func=FUNCTIONS['strict_brep_hole_evidence']
        imports=[n for n in ast.walk(func) if isinstance(n,ast.ImportFrom)]
        self.assertTrue(any(n.module=='OCP.BRepClass3d' for n in imports))
        self.assertTrue(any(n.module=='OCP.STEPControl' for n in imports))
        server=BACKEND.read_text(encoding="utf8")
        start=server.index('def process_job(')
        end=server.index('def capabilities(',start)
        body=server[start:end]
        self.assertLess(body.index('strict_brep_hole_evidence(file_path,sha)'),
                        body.index('file_path.unlink(missing_ok=True)'))
        self.assertIn('hole_evidence=hole_evidence',body)
        self.assertIn("if engine=='ocp':",body)

    def test_endpoint_requires_active_sha_and_never_overrides_ml(self):
        server=BACKEND.read_text(encoding="utf8")
        self.assertIn("if path.startswith('/api/geometry/hole-evidence/'):",server)
        start=server.index("if path.startswith('/api/geometry/hole-evidence/'):")
        end=server.index("if path.startswith('/api/geometry/dimensions/'):",start)
        endpoint=server[start:end]
        self.assertIn("CURRENT.get('job_id')!=uid",endpoint)
        self.assertIn("qa_strict_hole_evidence(data,job.get('sha256'))",endpoint)
        self.assertNotIn('ML_JOBS[',endpoint)
        self.assertNotIn('FEA_JOBS[',endpoint)

if __name__=='__main__':unittest.main()
