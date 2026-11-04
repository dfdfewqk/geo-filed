"""DeepSeek receives numerical original-vs-D6 observations only when ON.

Isolated actual production function; no solver, SQLite, network or paid calls.
"""
import ast
import json
import math
from pathlib import Path
import unittest

SOURCE=(Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py").read_text(encoding="utf8")
NODE=next(n for n in ast.parse(SOURCE).body if isinstance(n,ast.FunctionDef)
          and n.name=="gf_agent_llm_optional")
SCOPE={"math":math}
exec(compile(ast.fix_missing_locations(ast.Module(body=[NODE],type_ignores=[])),
             "GeoField_CAD_Analysis.py","exec"),SCOPE)
SCOPE["gf_agent_llm_config"]=lambda env:{
    "configured":True,"provider":"deepseek","selected_model":"deepseek-flash",
    "timeout_seconds":60}
SHA_A="a"*64
SHA_B="b"*64
RUN1="1"*32
RUN2="2"*32

def proof():
    return {
      "schema":"geofield-d6-two-geometry-descriptive-v1",
      "status":"two_different_cad_real_solver_runs_descriptive_only",
      "read_only":True,
      "source":"original_and_server_generated_D6_step_sha_bound",
      "original":{"cad_sha256":SHA_A,"run_id":RUN1,
                  "max_stress_mpa":20.,"max_displacement_mm":.030},
      "variant":{"cad_sha256":SHA_B,"run_id":RUN2,
                 "max_stress_mpa":18.,"max_displacement_mm":.027},
      "stress_change":{"original":20.,"variant":18.,"absolute_difference":-2.},
      "displacement_change":{"original":.03,"variant":.027,"absolute_difference":-.003},
      "fixed_and_loaded_surface_equivalence_verified":False,
      "reaction_and_applied_moment_equivalence_verified":False,
      "support_location_screen_passed":True,
      "applied_load_moment_screen_passed":True,
      "physical_load_screen":{
        "support_bbox_max_drift_mm":0.01,
        "load_bbox_max_drift_mm":0.02,
        "load_center_distance_mm":0.03,
        "resultant_drift_n":0.001,
        "load_moment_change_n_mm":0.02,
        "load_moment_equivalent_lever_arm_change_mm":0.001},
      "mesh_convergence_certified":False,
      "design_improvement_verified":False,
      "structural_safety_certified":False}
def agent(geometry):
    return {"schema":"geofield-evidence-agent-v1",
      "cad_sha256":SHA_B,
      "cad":{"findings_count":4},"ml":{"status":"research_unverified"},
      "fea":{"status":"INP_STA_FRD_reverified",
             "maximum_von_mises_mpa":18.,"maximum_displacement_mm":.027,
             "element_type":"C3D4"},"d6_comparison_context":geometry}

class OptedInD6AI(unittest.TestCase):
    def request(self,selection,opt_in):
        seen=[]
        def send(payload,key):
            seen.append(payload)
            self.assertEqual(key,"TEST-ONLY-SECRET")
            return {"choices":[{"finish_reason":"stop",
                       "message":{"content":"비교 수치 참고. 설계 개선 미검증."}}]}
        result=SCOPE["gf_agent_llm_optional"](
             agent(selection),opt_in=opt_in,
             environ={"DEEPSEEK_API_KEY":"TEST-ONLY-SECRET"},transport=send)
        return result,seen

    def test_on_sends_only_allowlisted_descriptive_numbers(self):
        result,calls=self.request(proof(),True)
        self.assertTrue(result["connected"])
        self.assertEqual(len(calls),1)
        payload=calls[0]
        self.assertIn("different CAD STEP sources",payload["messages"][0]["content"])
        values=json.loads(payload["messages"][1]["content"])
        actual=values["verified_d6_geometry_comparison"]
        self.assertEqual(actual["original_hole_diameter_mm"],5.5)
        self.assertEqual(actual["variant_hole_diameter_mm"],6.)
        self.assertEqual(actual["original_max_stress_mpa"],20.)
        self.assertEqual(actual["variant_max_stress_mpa"],18.)
        for k in ("supports_and_load_moments_equivalent_verified",
                  "geometry_improvement_verified","convergence_certified","safety_certified"):
            self.assertFalse(actual[k])
        text=json.dumps(payload)
        for forbidden in (SHA_A,SHA_B,RUN1,RUN2,"TEST-ONLY-SECRET","case_sha256",
                          "snapshot_id","fixed_faces","load_faces"):
            self.assertNotIn(forbidden,text)

    def test_off_zero_paid_requests(self):
        result,calls=self.request(proof(),False)
        self.assertFalse(result["executed"])
        self.assertEqual(calls,[])

    def test_unverified_physical_equivalence_claim_is_rejected(self):
        for bad in ({**proof(),"design_improvement_verified":True},
                    {**proof(),"fixed_and_loaded_surface_equivalence_verified":True},
                    {**proof(),"stress_change":{**proof()["stress_change"],"original":999.}}):
            with self.subTest(bad=bad):
                result,calls=self.request(bad,True)
                self.assertEqual(len(calls),1)
                values=json.loads(calls[0]["messages"][1]["content"])
                self.assertNotIn("verified_d6_geometry_comparison",values)

if __name__=="__main__":
    unittest.main()
