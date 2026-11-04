"""Regression: the verified report must never silently reuse paid AI text.

The old global AI reply cache and disconnected report appendix formatter are
gone. Read-only: no network, API keys, FEA, SQLite, or browser.
"""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
BACKEND=(ROOT/"payload"/"GeoField_CAD_Analysis.py").read_text(encoding="utf8")
UI=(ROOT/"payload"/"frontend"/"cad.js").read_text(encoding="utf8")
TREE=ast.parse(BACKEND)
REPORT=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)
            and n.name=="gf_current_verified_report")
REPORT_SOURCE=ast.get_source_segment(BACKEND,REPORT) or ""
START=UI.index("function gfReportReady(")
END=UI.index("$('collapseBtn').onclick",START)
VIEW=UI[START:END]


class ExternalReportBindingTests(unittest.TestCase):
    def test_old_server_cache_and_dead_formatter_removed(self):
        self.assertNotIn("GF_AGENT_EXTERNAL_REPORT",BACKEND)
        self.assertNotIn("def gf_external_report_section(",BACKEND)
        self.assertNotIn("gf_external_report_section",REPORT_SOURCE)
        self.assertNotIn("gf_agent_llm_optional(",REPORT_SOURCE)
        self.assertIn("report=html_report(summary)",REPORT_SOURCE)
        self.assertIn("report=gf_render_live_agent_report(report,summary,agent)",
                      REPORT_SOURCE)
        self.assertIn("append_verified_evidence(report,summary,provenance,case",
                      REPORT_SOURCE)

    def test_server_rechecks_real_cad_case_and_solver(self):
        for required in (
            "gf_verified_analysis_report_ready(summary,provenance)",
            "qa_report_active_run_unchanged(uid,job['sha256']",
            "latest_case=r181_current_result_case(uid)",
            "provenance['verified_run_id']",
        ):
            self.assertIn(required,REPORT_SOURCE)
        self.assertIn("report=gf_append_local_hole_report(",REPORT_SOURCE)

    def test_paid_report_needs_explicit_one_shot_and_current_run(self):
        self.assertIn("const includeAI=toggle?.checked===true",VIEW)
        self.assertIn("if(toggle)toggle.checked=false;",VIEW)
        self.assertIn("if(!includeExternal)",VIEW)
        self.assertIn("'X-GeoField-LLM-Opt-In':'1'",VIEW)
        self.assertIn("answer.fea.run_id===run&&answer.fea.case_sha256===caseSha",VIEW)
        self.assertIn("gfReportSelectionCurrent(uid,sha,run,caseSha)",VIEW)
        self.assertIn("if(!response.ok)throw Error(",VIEW)
        self.assertIn("'geofield-optional-external-ai'",VIEW)
        self.assertIn("if(stale)stale.remove();",VIEW)

    def test_ai_text_escaped_and_failure_preserves_solver_html(self):
        self.assertIn("description.textContent=llm.explanation",VIEW)
        self.assertNotIn("description.innerHTML=llm.explanation",VIEW)
        self.assertIn("외부 AI 설명을 받지 못했습니다",VIEW)
        self.assertIn("기존 CAD·FEA와 로컬 규칙 보고서는 정상적으로 유지됩니다",VIEW)
        self.assertIn("parsed.documentElement.outerHTML",VIEW)

    def test_ai_off_keeps_original_server_save(self):
        self.assertIn("'/api/results/report-save/'+encodeURIComponent(uid)",VIEW)
        self.assertIn("'X-GeoField-Report-Export':'EXPLICIT_SAVE'",VIEW)
        self.assertIn("if(!includeAI)",VIEW)
        self.assertIn("URL.createObjectURL(blob)",VIEW)
        self.assertIn("원본 보고서는 보존",VIEW)


if __name__=="__main__":
    unittest.main()
