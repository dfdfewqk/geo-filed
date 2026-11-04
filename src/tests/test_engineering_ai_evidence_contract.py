"""Read-only proof for the richer optional engineering AI prompt.

No real FEA solve, DeepSeek requests, secrets, or user files.
"""
import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "payload" / "GeoField_CAD_Analysis.py"
SOURCE = ROOT.read_text(encoding="utf8")
TREE = ast.parse(SOURCE)
NAMES = {"gf_ai_verified_engineering_context", "gf_agent_llm_optional"}
FUNCS = [x for x in TREE.body if isinstance(x, ast.FunctionDef) and x.name in NAMES]
assert {x.name for x in FUNCS} == NAMES, "expected production functions are missing"
scope = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=FUNCS, type_ignores=[])),
             str(ROOT), "exec"), scope)
scope["gf_agent_llm_config"] = lambda env: {
    "configured": True, "provider": "deepseek",
    "selected_model": "deepseek-flash", "timeout_seconds": 60,
}

SHA = "a" * 64
CASE = "b" * 64
RUN = "2" * 32


def case():
    return {"cad_sha256": SHA, "case_sha256": CASE,
            "material": {"name": "NEVER_SEND_THIS_MATERIAL_NAME",
                         "young_modulus_mpa": 200000.0, "poisson_ratio": 0.3},
            "boundary_conditions": {"total_force_n": 49.05,
                                    "force_direction_unit": [0, 0, -1],
                                    "fixed_face_ids": [1, 2], "load_face_ids": [3]},
            "mesh_request": {"target_element_size_mm": 1.833},
            "file": "NEVER_SEND_THIS_STEP_FILE_PATH"}


def agent():
    return {"schema": "geofield-evidence-agent-v1",
            "cad_sha256": SHA, "cad": {"findings_count": 4},
            "fea": {"status": "INP_STA_FRD_reverified", "run_id": RUN,
                    "case_sha256": CASE, "maximum_von_mises_mpa": 18.447721,
                    "maximum_displacement_mm": 0.03300654,
                    "element_type": "C3D4"},
            "ml": {"status": "research_unverified"},
            "fea_spatial": {"status": "verified_frd_surface_peak_positions",
                            "cad_sha256": SHA, "case_sha256": CASE, "run_id": RUN,
                            "cad_face_attribution_verified": False,
                            "stress_peak": {
                                "source": "reverified_actual_calculix_surface_nodes",
                                "value": 17.1, "position_mm": [7, 6, 0]}}}


class EngineeringAIContractTests(unittest.TestCase):
    def test_verified_conditions_and_bounded_explanation(self):
        obj = agent()
        obj["engineering_context"] = scope["gf_ai_verified_engineering_context"](obj, case())
        self.assertEqual(obj["engineering_context"]["verified_surface_peak_mpa"], 17.1)
        calls = []
        explanation = "[1. 응력 집중 검토] " + "추가 검증 필요. " * 200
        self.assertGreater(len(explanation), 1600)
        self.assertLess(len(explanation), 3500)
        def fake(payload, secret):
            calls.append(payload)
            self.assertEqual(secret, "TEST-SECRET-NEVER-COMMIT")
            return {"choices": [{"finish_reason": "stop",
                                 "message": {"content": explanation}}]}
        result = scope["gf_agent_llm_optional"](
            obj, opt_in=True, environ={"DEEPSEEK_API_KEY": "TEST-SECRET-NEVER-COMMIT"},
            transport=fake)
        self.assertTrue(result["connected"])
        self.assertEqual(result["explanation"], explanation.strip())
        self.assertEqual(len(calls), 1)
        payload = calls[0]
        self.assertEqual(payload["max_tokens"], 1150)
        instructions = payload["messages"][0]["content"]
        for heading in ("[1. 응력 집중 검토]", "[2. 재료·하중 평가]",
                        "[3. 설계 개선 가설]", "[4. 추가 해석·검증 순서]"):
            self.assertIn(heading, instructions)
        values = json.loads(payload["messages"][1]["content"])
        self.assertEqual(values["fea_max_von_mises_mpa"], 18.447721)
        self.assertEqual(values["verified_load_material_context"]["applied_force_n"], 49.05)
        self.assertIsNone(values["verified_load_material_context"]["yield_strength_mpa"])
        raw = json.dumps(payload)
        for forbidden in ("NEVER_SEND_THIS_MATERIAL_NAME", "NEVER_SEND_THIS_STEP_FILE_PATH",
                          "TEST-SECRET-NEVER-COMMIT", SHA, CASE, RUN, "position_mm"):
            self.assertNotIn(forbidden, raw)

    def test_stale_case_and_local_only_stay_safe(self):
        obj = agent()
        stale = case()
        stale["case_sha256"] = "f" * 64
        self.assertIsNone(scope["gf_ai_verified_engineering_context"](obj, stale))
        calls = []
        reply = scope["gf_agent_llm_optional"](
            obj, opt_in=False, transport=lambda *args: calls.append(args))
        self.assertFalse(reply["executed"])
        self.assertEqual(calls, [])

    def test_active_provider_reply_guard_is_3500_chars(self):
        self.assertEqual(SOURCE.count("not 0<len(explanation.strip())<=3500"), 1)
        self.assertNotIn("gf_external_report_section(",SOURCE)
        self.assertNotIn("not 0<len(explanation.strip())<=1600", SOURCE)


if __name__ == "__main__":
    unittest.main()
