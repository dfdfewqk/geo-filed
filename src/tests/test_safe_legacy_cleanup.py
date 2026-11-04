"""Ensure safe legacy cleanup does not remove active GeoField workflows.

Source-only regression: no network, solver, API key, or engineering data.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = (ROOT / "payload" / "GeoField_CAD_Analysis.py").read_text(encoding="utf8")
FRONTEND = (ROOT / "payload" / "frontend" / "cad.js").read_text(encoding="utf8")
HTML = (ROOT / "payload" / "frontend" / "index.html").read_text(encoding="utf8")


class SafeLegacyCleanupTests(unittest.TestCase):
    def test_old_unimplemented_ai_stub_removed_without_touching_real_route(self):
        self.assertNotIn("if path=='/api/ai/run':", BACKEND)
        self.assertNotIn("외부 AI 연결 미구현", BACKEND)
        self.assertIn("if path.startswith('/api/agent/evidence/'):", BACKEND)
        self.assertIn("gf_agent_llm_optional(response,opt_in=True)", BACKEND)
        self.assertIn("gf_external_report_section(", BACKEND)
        self.assertIn("'/api/agent/evidence/'+expected+'?llm=1'", FRONTEND)

    def test_unreferenced_old_port_scanner_removed(self):
        defs = [n.name for n in ast.parse(BACKEND).body if isinstance(n, ast.FunctionDef)]
        self.assertNotIn("free_port", defs)
        self.assertIn("gf_agent_llm_optional", defs)
        self.assertIn("gf_current_verified_report", defs)

    def test_old_external_ai_disclosure_duplicate_removed_without_removing_history(self):
        self.assertNotIn("고급 · 연구용 ML 및 외부 LLM 참고 설명 (선택)", HTML)
        self.assertIn("고급 · 연구용 ML 진단 (선택)", HTML)
        self.assertEqual(HTML.count('id="optionalResearchAndExternal"'), 1)
        self.assertEqual(HTML.count('id="agentOptionalExternal"'), 1)
        self.assertEqual(HTML.count('id="agentLLMOptIn"'), 1)
        self.assertIn('id="legacyRecordTools"', HTML)
        self.assertIn('id="previousResearchTools"', HTML)
        self.assertIn("if(pane==='records')", FRONTEND)

    def test_engineering_ai_limits_and_paid_opt_in_still_gated(self):
        self.assertIn("GEOFIELD_ENGINEERING_AI_V1_20261104", BACKEND)
        self.assertEqual(BACKEND.count("not 0<len(explanation.strip())<=3500"), 2)
        self.assertIn("X-GeoField-LLM-Opt-In", FRONTEND)
        self.assertIn("const externalOptIn=!automaticLocal&&$('agentLLMOptIn')?.checked===true;", FRONTEND)
        self.assertIn("gfAutoLocalOnly", FRONTEND)


if __name__ == "__main__":
    unittest.main()
