"""Local OCC hole evidence is separate from BrepMFR/R12 and bound to CAD SHA.

Extract real production code. No private STEP, solver, ML weights, network, SQLite.
"""
import ast
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"payload"/"GeoField_CAD_Analysis.py").read_text(encoding="utf8")
TREE=ast.parse(SOURCE)
NAMES={"qa_strict_hole_evidence","gf_verified_hole_summary",
       "gf_append_local_hole_report","gf_agent_llm_optional"}
FUNCTIONS=[f for f in TREE.body if isinstance(f,ast.FunctionDef) and f.name in NAMES]
assert {f.name for f in FUNCTIONS}==NAMES
SCOPE={}
exec(compile(ast.fix_missing_locations(ast.Module(body=FUNCTIONS,type_ignores=[])),
             "GeoField_CAD_Analysis.py","exec"),SCOPE)
SHA="a"*64
CASE="b"*64
RUN="2"*32

def local_evidence():
    return {"schema":"geofield-hole-occupancy-v1",
            "source":"local_ocp_solid_occupancy_not_ml",
            "sha256":SHA,"viewer_face_mapping_verified":False,
            "decision_usage":"cad_diagnostic_only_not_fea_or_safety",
            "status":"complete",
            "faces":[
              {"face_ordinal":1,"state":"through_hole","radius_mm":2.75},
              {"face_ordinal":2,"state":"through_hole","radius_mm":2.75},
              {"face_ordinal":3,"state":"through_hole","radius_mm":2.75},
              {"face_ordinal":4,"state":"through_hole","radius_mm":2.75},
              {"face_ordinal":5,"state":"blind_hole","radius_mm":2.2},
              {"face_ordinal":6,"state":"unverified"}]}

class HoleReportIntegration(unittest.TestCase):
    def test_four_through_faces_and_one_blind_face_in_report(self):
        compact=SCOPE["gf_verified_hole_summary"](local_evidence(),SHA)
        self.assertEqual(compact["through_cylindrical_face_count"],4)
        self.assertEqual(compact["blind_cylindrical_face_count"],1)
        self.assertEqual(compact["unverified_cylindrical_face_count"],1)
        self.assertFalse(compact["unique_drilled_hole_count_verified"])
        html=SCOPE["gf_append_local_hole_report"](
            "<html><body><h1>검증된 FEA 결과</h1></body></html>",compact)
        self.assertIn("검증된 FEA 결과",html)
        self.assertIn("관통 4면 · 막힘 1면 · 미확정 1면",html)
        self.assertIn("BrepMFR/R12 ML 정확도",html)
        self.assertEqual(html.count('id="geofield-local-hole-evidence"'),1)

    def test_stale_and_unverified_never_misrepresented_as_zero(self):
        for bad in ({**local_evidence(),"sha256":"f"*64},
                    {**local_evidence(),"source":"brepmfr_epoch43"},
                    {**local_evidence(),"status":"unverified"},
                    None):
            with self.subTest(bad=bad):
                summary=SCOPE["gf_verified_hole_summary"](bad,SHA)
                self.assertIsNone(summary)
                html=SCOPE["gf_append_local_hole_report"](
                    "<body>실제 FEA</body>",summary)
                self.assertIn("확인 불가",html)
                self.assertNotIn("관통 0면",html)
                self.assertIn("실제 FEA",html)

    def test_raw_ml_labels_are_not_converted_to_hole_facts(self):
        invalid=local_evidence()
        invalid["faces"][0]["state"]="blind_hole_ml"
        self.assertIsNone(SCOPE["gf_verified_hole_summary"](invalid,SHA))
        invalid=local_evidence()
        invalid["viewer_face_mapping_verified"]=True
        self.assertIsNone(SCOPE["gf_verified_hole_summary"](invalid,SHA))

    def test_ai_payload_is_counts_only_and_opt_in_only(self):
        SCOPE["gf_agent_llm_config"]=lambda env:{
            "configured":True,"provider":"deepseek","selected_model":"deepseek-flash"}
        compact=SCOPE["gf_verified_hole_summary"](local_evidence(),SHA)
        agent={"schema":"geofield-evidence-agent-v1","cad_sha256":SHA,
               "cad":{"findings_count":4},"ml":{"status":"research_unverified"},
               "fea":{"status":"INP_STA_FRD_reverified","run_id":RUN,
                      "case_sha256":CASE,"element_type":"C3D4",
                      "maximum_von_mises_mpa":18.4,
                      "maximum_displacement_mm":0.033},
               "hole_geometry_summary":compact}
        seen=[]
        def fake(payload,key):
            seen.append(payload)
            return {"choices":[{"finish_reason":"stop",
                                "message":{"content":"관통 원통면 4개는 고유 홀 개수가 아닙니다."}}]}
        cfg={"DEEPSEEK_API_KEY":"synthetic-key-do-not-send"}
        no=SCOPE["gf_agent_llm_optional"](agent,opt_in=False,environ=cfg,transport=fake)
        self.assertFalse(no["executed"])
        self.assertEqual(len(seen),0)
        out=SCOPE["gf_agent_llm_optional"](agent,opt_in=True,environ=cfg,transport=fake)
        self.assertEqual(len(seen),1)
        self.assertTrue(out["executed"])
        values=json.loads(seen[0]["messages"][1]["content"])
        self.assertEqual(values["verified_brep_cylindrical_face_counts"],
            {"through_cylindrical_face_count":4,
             "blind_cylindrical_face_count":1,
             "unverified_cylindrical_face_count":1})
        raw=json.dumps(seen[0])
        for forbidden in (SHA,CASE,RUN,"face_ordinal","radius_mm",
                          "unique_drilled_hole_count_verified","synthetic-key-do-not-send"):
            self.assertNotIn(forbidden,raw)
        agent["hole_geometry_summary"]=None
        seen.clear()
        SCOPE["gf_agent_llm_optional"](agent,opt_in=True,environ=cfg,transport=fake)
        values=json.loads(seen[0]["messages"][1]["content"])
        self.assertNotIn("verified_brep_cylindrical_face_counts",values)

    def test_report_and_freecad_optional_probe_are_preserved(self):
        self.assertIn("report=gf_append_local_hole_report(",SOURCE)
        self.assertIn("if engine in ('ocp','freecad'):",SOURCE)
        self.assertIn("strict_brep_hole_evidence(file_path,sha)",SOURCE)
        self.assertIn("job.get('hole_evidence')",SOURCE)
        self.assertIn("return {'html':report",SOURCE)


if __name__=="__main__":
    unittest.main()
