"""Real production signed-case TOCTOU guard and FEA server race regression.

Uses disposable case files, no Windows runtime, user STEP or CalculiX.
"""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf8"))
MATCHES=[x for x in TREE.body if isinstance(x,ast.FunctionDef)
         and x.name=="r20_fea_uploaded_case_matches"]
assert len(MATCHES)==1,"Production FEA signed-case upload guard missing"
scope={"hashlib":hashlib,"json":json}
exec(compile(ast.fix_missing_locations(ast.Module(body=MATCHES,type_ignores=[])),
             str(SOURCE),"exec"),scope)
guard=scope["r20_fea_uploaded_case_matches"]
CAD="a"*64
CASE="b"*64

class SignedCaseUploadRegression(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.file=self.root/"saved.fea_case.json"
        self.payload={"cad_sha256":CAD,"case_sha256":CASE,"mesh_request":{
            "element_type":"C3D4"},"material":{"name":"SUS304"},
            "boundary_conditions":{"total_force_n":49.03325}}
        self.save()

    def save(self):
        self.file.write_text(json.dumps(self.payload,sort_keys=True),encoding="utf8")
        self.sha=hashlib.sha256(self.file.read_bytes()).hexdigest()

    def test_same_signed_case_survives_step_upload(self):
        self.assertTrue(guard(self.file,self.sha,CAD,CASE))

    def test_changed_material_or_load_must_not_launch_old_case(self):
        old=self.sha
        self.payload["boundary_conditions"]["total_force_n"]=99
        self.save()
        self.assertFalse(guard(self.file,old,CAD,CASE))
        self.assertTrue(guard(self.file,self.sha,CAD,CASE))

    def test_even_rewritten_same_case_json_must_not_pass_byte_identity(self):
        old=self.sha
        self.file.write_text(json.dumps(self.payload,indent=2),encoding="utf8")
        self.assertFalse(guard(self.file,old,CAD,CASE))

    def test_case_and_cad_identity_must_both_match(self):
        self.assertFalse(guard(self.file,self.sha,CAD,"c"*64))
        self.assertFalse(guard(self.file,self.sha,"d"*64,CASE))
        self.assertFalse(guard(self.file,"z"*64,CAD,CASE))

    def test_missing_or_corrupted_case_never_approves(self):
        old=self.sha
        self.file.write_bytes(b'not json')
        self.assertFalse(guard(self.file,old,CAD,CASE))
        self.file.unlink()
        self.assertFalse(guard(self.file,old,CAD,CASE))

    def test_symlink_is_never_used_for_approved_fea_case(self):
        target=self.file
        linked=self.root/"case-link.json"
        try:linked.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest("Symlinks unsupported")
        self.assertFalse(guard(linked,self.sha,CAD,CASE))
        self.assertTrue(target.exists())

    def test_server_checks_case_after_upload_before_starting_calculix(self):
        funcs={x.name:x for x in TREE.body if isinstance(x,ast.ClassDef)}
        target=None
        for c in funcs.values():
            for node in c.body:
                if isinstance(node,ast.FunctionDef) and node.name=="receive_fea_step":
                    target=node
        self.assertIsNotNone(target)
        body=ast.get_source_segment(SOURCE.read_text(encoding="utf8"),target)
        pos_guard=body.find("r20_fea_uploaded_case_matches(")
        pos_enqueue=body.find("FEA_JOBS[rid]=")
        pos_spawn=body.find("threading.Thread(")
        self.assertTrue(0<pos_guard<pos_enqueue<pos_spawn)
        self.assertIn("approved_case_file_sha",body)
        self.assertIn("for v in FEA_JOBS.values()",body)
        self.assertIn("for v in MESH_STUDIES.values()",body)
        self.assertIn("STEP 업로드 중 저장된 FEA",body)

if __name__=="__main__":unittest.main()
