"""Regress the exact 2026-11-04 user report: real FEA but no optional studies.

Production AST-extracted DeepSeek wrapper, synthetic transport only.
No network, API spending, solver, private STEP or persistence.
"""
import ast
import json
import math
import os
import re
from pathlib import Path
import unittest

SRC=(Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py").read_text(encoding="utf8")
FN=next(x for x in ast.parse(SRC).body
        if isinstance(x,ast.FunctionDef) and x.name=="gf_agent_llm_optional")
GLOBALS={}
exec(compile(ast.fix_missing_locations(ast.Module(body=[FN],type_ignores=[])),
             "GeoField_CAD_Analysis.py","exec"),GLOBALS)
GLOBALS["gf_agent_llm_config"]=lambda env:{
    "configured":True,"provider":"deepseek","selected_model":"deepseek-chat",
    "timeout_seconds":45}
CAD="a"*64
CASE="b"*64
RUN="2"*32

def source_evidence():
    return {
      "schema":"geofield-evidence-agent-v1",
      "cad_sha256":CAD,
      "cad":{"findings_count":4},
      "ml":{"status":"research_unverified"},
      "fea":{"status":"INP_STA_FRD_reverified","run_id":RUN,
             "case_sha256":CASE,"maximum_von_mises_mpa":11.11,
             "maximum_displacement_mm":0.02066,"element_type":"C3D4"},
      "hole_geometry_summary":{
          "source":"local_ocp_solid_occupancy_not_ml","status":"complete",
          "through_cylindrical_face_count":4,
          "blind_cylindrical_face_count":0,
          "unverified_cylindrical_face_count":0,
          "unique_drilled_hole_count_verified":False,
          "mechanical_cause_verified":False},
      "engineering_context":{
          "source":"verified_fea_case_numeric_only",
          "young_modulus_mpa":193000.,
          "poisson_ratio":0.29,
          "applied_force_n":29.42,
          "force_direction_unit":[0.,0.,1.],
          "fixed_face_count":1,
          "loaded_face_count":1,
          "target_mesh_size_mm":1.192,
          "verified_surface_peak_mpa":11.11,
          "yield_strength_mpa":None,
          "stress_location_cause_verified":False}}

def request(text, *, attached=None, opt_in=True):
    payloads=[]
    def transport(payload,key):
        payloads.append(payload)
        assert key=="TEST-ONLY-NOT-REAL-API-KEY"
        return {"choices":[{"finish_reason":"stop",
                 "message":{"content":text}}]}
    evidence=source_evidence()
    if attached:
        evidence.update(attached)
    outcome=GLOBALS["gf_agent_llm_optional"](
        evidence,opt_in=opt_in,
        environ={"DEEPSEEK_API_KEY":"TEST-ONLY-NOT-REAL-API-KEY"},
        transport=transport)
    return outcome,payloads

class EvidenceClarityRegression(unittest.TestCase):
    def test_current_verified_observations_not_declared_all_unknown(self):
        result,calls=request(
            "[1. 응력 집중 검토] 실제 FEA 최대 11.11 MPa, 변위 0.02066mm 확인. "
            "[2. 재료·하중 평가] 29.42N +Z, 영률 193000MPa. "
            "[3. 설계 개선 가설] 홀 주변 국부 메시를 먼저 검사합니다. "
            "[4. 추가 해석·검증 순서] 메시 3단계와 D6 재계산을 순서대로 합니다.")
        self.assertTrue(result["connected"])
        self.assertEqual(len(calls),1)
        prompt=calls[0]["messages"][0]["content"]
        outbound=json.loads(calls[0]["messages"][1]["content"])
        scope=outbound["verification_scope"]
        self.assertTrue(scope["current_fea_inp_sta_frd_reverified"])
        self.assertFalse(scope["same_geometry_three_mesh_study_attached"])
        self.assertFalse(scope["d6_original_variant_comparison_attached"])
        self.assertFalse(scope["d6_inp_support_load_screen_passed"])
        self.assertFalse(scope["yield_strength_supplied"])
        self.assertEqual(outbound["fea_max_von_mises_mpa"],11.11)
        self.assertEqual(outbound["fea_max_displacement_mm"],0.02066)
        self.assertEqual(outbound["verified_load_material_context"]["applied_force_n"],29.42)
        self.assertEqual(outbound["verified_brep_cylindrical_face_counts"]["through_cylindrical_face_count"],4)
        self.assertNotIn("verified_mesh_followup",outbound)
        self.assertNotIn("verified_d6_geometry_comparison",outbound)
        self.assertIn("NEVER claim D6 INP screening passed",prompt)
        self.assertIn("actual fea",prompt.lower())
        self.assertIn("not a failed experiment",prompt.lower())
        self.assertIn("SAME-GEOMETRY mesh study",prompt)
        self.assertIn("different CAD STEP sources",prompt)
        self.assertNotIn("TEST-ONLY-NOT-REAL-API-KEY",json.dumps(calls))

    def test_exact_screenshot_hallucinated_inp_screen_pass_blocked(self):
        model="[1. 응력 집중 검토] 11.11 MPa. [2. 재료·하중 평가] 29.42 N. " \
              "[3. 설계 개선 가설] 홀 검토. [4. 추가 해석·검증 순서] " \
              "JSON에는 verified_d6_geometry_comparison 및 verified_mesh_followup 데이터가 없어 " \
              "형상 간 비교는 수행할 수 없다. INP의 고정/하중 공간·모멘트 스크리닝은 통과했으나, " \
              "CAD 면 대응 및 반력 등가성은 미인증이다."
        result,calls=request(model)
        self.assertEqual(len(calls),1)
        self.assertFalse(result["connected"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["status"],"invalid_response")
        self.assertIsNone(result["explanation"])

    def test_d6_screen_is_allowed_only_with_valid_independent_pair(self):
        proof={
          "schema":"geofield-d6-two-geometry-descriptive-v1",
          "status":"two_different_cad_real_solver_runs_descriptive_only",
          "read_only":True,
          "source":"original_and_server_generated_D6_step_sha_bound",
          "original":{"cad_sha256":"c"*64,"max_stress_mpa":13.,
                      "max_displacement_mm":0.025},
          "variant":{"cad_sha256":CAD,"max_stress_mpa":11.11,
                     "max_displacement_mm":0.02066},
          "stress_change":{"original":13.,"variant":11.11},
          "displacement_change":{"original":0.025,"variant":0.02066},
          "physical_load_screen":{
              "support_bbox_max_drift_mm":0.01,
              "load_bbox_max_drift_mm":0.02,
              "load_center_distance_mm":0.03,
              "resultant_drift_n":0.001,
              "load_moment_change_n_mm":0.01,
              "load_moment_equivalent_lever_arm_change_mm":0.01},
          "fixed_and_loaded_surface_equivalence_verified":False,
          "reaction_and_applied_moment_equivalence_verified":False,
          "support_location_screen_passed":True,
          "applied_load_moment_screen_passed":True,
          "mesh_convergence_certified":False,
          "design_improvement_verified":False,
          "structural_safety_certified":False}
        message="원본과 변경본 각각 재해석된 INP의 고정/하중 공간·모멘트 스크리닝은 통과했으나 전체 CAD 면 동등성은 단정할 수 없습니다."
        result,calls=request(message,attached={"d6_comparison_context":proof})
        self.assertTrue(result["connected"])
        outbound=json.loads(calls[0]["messages"][1]["content"])
        self.assertTrue(outbound["verification_scope"]["d6_original_variant_comparison_attached"])
        self.assertTrue(outbound["verification_scope"]["d6_inp_support_load_screen_passed"])
        self.assertIn("verified_d6_geometry_comparison",outbound)
        self.assertFalse(outbound["verified_d6_geometry_comparison"]["geometry_improvement_verified"])

    def test_ai_off_never_calls_provider(self):
        result,calls=request("Any message",opt_in=False)
        self.assertFalse(result["executed"])
        self.assertEqual(calls,[])

if __name__=="__main__":
    unittest.main()
