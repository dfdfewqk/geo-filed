"""GeoField L-bracket D6 copy: strict input, no overwrite, no FEA/AI/SQLite.

Synthetic, optional OCP solid test and stdlib-only HTTP security/identity tests.
The user's private STEP and FEA history are never used in CI.
"""
from __future__ import annotations
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import threading
import types
import tempfile
import unittest
import importlib.util

BACKEND=(Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py")
SOURCE=BACKEND.read_text(encoding="utf8")
TREE=ast.parse(SOURCE)
NAMES={"strict_brep_hole_evidence","qa_strict_hole_evidence",
       "gf_lbracket_make_d6_copy"}
NODES=[x for x in TREE.body if isinstance(x,ast.FunctionDef) and x.name in NAMES]
assert {x.name for x in NODES}==NAMES, "Expected original OCP and variant functions"
HANDLER=next(x for x in TREE.body if isinstance(x,ast.ClassDef) and x.name=="Handler")
METHOD=next(x for x in HANDLER.body if isinstance(x,ast.FunctionDef)
            and x.name=="receive_lbracket_d6_copy")
SCOPE={"Path":Path,"hashlib":hashlib}
SCOPE["file_sha256"]=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
exec(compile(ast.fix_missing_locations(ast.Module(body=NODES+[METHOD],type_ignores=[])),
             str(BACKEND),"exec"),SCOPE)

UID="1"*32
ORIGIN_SHA="a"*64
COPY_BYTES=b"ISO-10303-21;\nDATA;\nTEST-GEOMETRY-COPY-ONLY;\nENDSEC;\n"


class VariantSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="geofield-copy-test-")
        self.addCleanup(self.tmp.cleanup)
        self.calls=[]
        self.scope=SCOPE.copy()
        self.scope.update({
            "STATE_LOCK":threading.RLock(),
            "JOBS_DIR":Path(self.tmp.name),
            "CURRENT":{"job_id":UID},
            "JOBS":{UID:{"status":"complete","filename":"L_bracket.step",
                          "sha256":ORIGIN_SHA}},
            "FEA_JOBS":{},
            "MESH_STUDIES":{},
            "ACTIVE":{"queued","running"},
            "valid_uid":lambda s:len(s)==32 and all(v in "0123456789abcdef" for v in s),
            "detect_ocp":lambda:True,
        })
        def change(src,sha,dest):
            self.calls.append((sha,Path(src).read_bytes()))
            Path(dest).write_bytes(COPY_BYTES)
            return {"source_sha256":sha,
                    "variant_sha256":hashlib.sha256(COPY_BYTES).hexdigest(),
                    "status":"geometry_only_verified_no_fea",
                    "needs_new_face_selection":True,
                    "structural_improvement_verified":False}
        self.scope["gf_lbracket_make_d6_copy"]=change
        source=b"ISO-10303-21;\n"+b"private-user-source-example"
        self.scope["JOBS"][UID]["sha256"]=hashlib.sha256(source).hexdigest()
        self.source=source
        self.sha=hashlib.sha256(source).hexdigest()
        self.scope["hashlib"]=hashlib
        self.method=types.FunctionType(SCOPE["receive_lbracket_d6_copy"].__code__,
                                         self.scope)

    def request(self, headers=None, data=None):
        raw=self.source if data is None else data
        base={
            "Content-Type":"application/octet-stream",
            "Content-Length":str(len(raw)),
            "X-GeoField-Variant-Confirm":"CREATE_D6_SEPARATE_STEP_ONLY",
            "X-GeoField-CAD-SHA256":self.sha,
            "Origin":"http://127.0.0.1:8600",
            "Sec-Fetch-Site":"same-origin"
        }
        if headers:base.update(headers)
        class Responder:
            def __init__(self):
                self.headers=base
                self.rfile=io.BytesIO(raw)
                self.server=types.SimpleNamespace(server_port=8600)
                self.response=None
            def fail(self,message,code=400):
                self.response={"error":str(message),"status_code":code}
                return self.response
            def send_raw(self,payload):
                self.response=payload
                return payload
        req=Responder()
        self.method(req,UID)
        return req.response

    def test_user_confirmed_same_sha_stays_non_destructive(self):
        got=self.request()
        self.assertEqual(got["status"],"geometry_only_verified_no_fea")
        self.assertEqual(base64.b64decode(got["step_base64"]),COPY_BYTES)
        self.assertEqual(self.calls[0],(self.sha,self.source))
        self.assertEqual(list(Path(self.tmp.name).iterdir()),[])

    def test_no_consent_and_cross_site_fail_before_body(self):
        for change in ({"X-GeoField-Variant-Confirm":"wrong"},
                       {"Sec-Fetch-Site":"cross-site"},
                       {"Origin":"https://malicious.example"}):
            with self.subTest(change=change):
                res=self.request(change)
                self.assertEqual(res["status_code"],403)
        self.assertEqual(self.calls,[])

    def test_changed_sha_stale_cad_and_running_solver_block(self):
        for update in (
            lambda: self.scope["CURRENT"].update(job_id="0"*32),
            lambda: self.scope["JOBS"][UID].update(sha256="f"*64),
            lambda: self.scope["FEA_JOBS"].update({"2"*32:{"status":"running"}}),
        ):
            with self.subTest(update=update):
                current=self.scope["CURRENT"].copy()
                jobs={k:v.copy() for k,v in self.scope["JOBS"].items()}
                fea=self.scope["FEA_JOBS"].copy()
                update()
                res=self.request()
                self.assertEqual(res["status_code"],409)
                self.scope["CURRENT"].clear();self.scope["CURRENT"].update(current)
                self.scope["JOBS"].clear();self.scope["JOBS"].update(jobs)
                self.scope["FEA_JOBS"].clear();self.scope["FEA_JOBS"].update(fea)
        self.assertEqual(self.calls,[])

    def test_wrong_payload_sha_and_size_cap_block(self):
        self.assertEqual(self.request(data=b"ISO-10303-21;WRONG-CONTENT-TEST")["status_code"],409)
        self.assertEqual(self.request(headers={"Content-Length":str(3*1024*1024)})["status_code"],413)
        self.assertEqual(self.calls,[])

    def test_no_persistent_solver_or_ai_side_effects_in_route(self):
        route=ast.get_source_segment(SOURCE,METHOD)
        self.assertIn("tempfile.TemporaryDirectory",route)
        self.assertIn("gf_lbracket_make_d6_copy",route)
        self.assertIn("X-GeoField-Variant-Confirm",route)
        self.assertNotIn("gf_agent_llm_optional(",route)
        self.assertNotIn("archive_current_job(",route)
        self.assertNotIn("run_real_fea(",route)
        self.assertNotIn("sqlite3.connect(",route)
        self.assertIn("if path.startswith('/api/cad/variant/lbracket-d6/'):",SOURCE)


_HAS_OCC=importlib.util.find_spec("OCP") is not None
_HAS_CQ=importlib.util.find_spec("cadquery") is not None


@unittest.skipUnless(_HAS_OCC and _HAS_CQ,"OCP/CadQuery optional synthetic geometry environment")
class SyntheticSolidGeometryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="geo-lbracket-d6-ocp-")
        self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/"L_bracket.step"
        self.target=Path(self.tmp.name)/"variant_D6.step"
        import cadquery as cq
        # Synthetic 50×30×50 L solid with four D5.5 full cylindrical holes.
        shape=(cq.Workplane("XY").box(50,30,5,centered=(False,False,False))
               .union(cq.Workplane("XY").box(5,30,50,centered=(False,False,False))))
        for x in (15,35):
            for y in (8,22):
                shape=shape.cut(cq.Workplane("XY").center(x,y).circle(2.75).extrude(5))
        cq.exporters.export(shape,str(self.source))
        self.original=self.source.read_bytes()
        self.sha=hashlib.sha256(self.original).hexdigest()

    def test_real_occ_boolean_and_post_export_geometric_reverification(self):
        report=SCOPE["gf_lbracket_make_d6_copy"](self.source,self.sha,self.target)
        self.assertEqual(report["status"],"geometry_only_verified_no_fea")
        self.assertEqual(report["through_cylindrical_faces"],4)
        self.assertEqual(report["source_sha256"],self.sha)
        self.assertNotEqual(report["variant_sha256"],self.sha)
        self.assertEqual(self.source.read_bytes(),self.original)
        self.assertFalse(report["structural_improvement_verified"])
        self.assertGreater(report["volume_reduction_mm3"],0)
        original_holes=SCOPE["strict_brep_hole_evidence"](self.source,self.sha)
        new_holes=SCOPE["strict_brep_hole_evidence"](self.target,report["variant_sha256"])
        self.assertEqual([x["radius_mm"] for x in original_holes["faces"]],[2.75]*4)
        self.assertEqual([x["radius_mm"] for x in new_holes["faces"]],[3.0]*4)
        self.assertEqual([x["state"] for x in new_holes["faces"]],["through_hole"]*4)
        with self.assertRaises(ValueError):
            SCOPE["gf_lbracket_make_d6_copy"](self.source,self.sha,self.target)

    def test_stale_sha_and_wrong_hole_geometry_rejected(self):
        with self.assertRaises(ValueError):
            SCOPE["gf_lbracket_make_d6_copy"](self.source,"f"*64,self.target)
        import cadquery as cq
        wrong=(cq.Workplane("XY").box(50,30,5,centered=(False,False,False))
               .union(cq.Workplane("XY").box(5,30,50,centered=(False,False,False)))
               .cut(cq.Workplane("XY").center(15,8).circle(2.75).extrude(5)))
        cq.exporters.export(wrong,str(self.source))
        bad_sha=hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            SCOPE["gf_lbracket_make_d6_copy"](self.source,bad_sha,self.target)
        self.assertFalse(self.target.exists())


if __name__=="__main__":
    unittest.main()
