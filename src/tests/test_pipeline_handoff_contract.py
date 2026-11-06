"""GeoField existing-pipeline contract and reproducible handoff inventory.

SOURCE/ARCHITECTURE test, NOT a claim that local paid AI or the user's Windows
runtime has been exercised. Known ML -> AI -> report gaps are logged (rather
than incorrectly 'passed') until the later integration stages fix them.
Read-only. Does not import paid clients, execute solver or modify user files.
"""
import re
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1]
JS = (SRC / 'payload/frontend/cad.js').read_text(encoding='utf-8')
SERVER = (SRC / 'payload/GeoField_CAD_Analysis.py').read_text(encoding='utf-8')
BRIDGE = (SRC / 'payload/ml_r12_bridge.py').read_text(encoding='utf-8')
DOCUMENT = (SRC.parent / 'docs/GEOFIELD_ML_AI_HANDOFF_AUDIT_20261106.md').read_text(encoding='utf-8')


def section(text, start, end):
    """Only assert inside the relevant production function/route."""
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[a:b]


class PipelineHandoffSourceContracts(unittest.TestCase):
    def test_cad_import_autostarts_two_existing_research_paths(self):
        frontend = section(JS, "$('importBtn').onclick=async()=>{", 'function resetModel(')
        self.assertIn('/api/cad/import?filename=', frontend)
        self.assertIn('auto_ml=', frontend)
        self.assertIn('watchAutoMl(', frontend)
        self.assertIn('watchAutoR12(', frontend)
        self.assertIn('obj.sha256!==s.analysis.sha256', frontend)
        self.assertIn('launch_automatic_ml(job,file_path)', SERVER)
        self.assertIn('launch_automatic_r12(job,file_path)', SERVER)
        self.assertIn('blocked_diagnostic_only', SERVER)
        self.assertIn('EXPECTED_MODEL_SHA256', BRIDGE)

    def test_existing_local_agent_and_paid_optin_are_separate(self):
        local = section(JS, 'function gfMaybeAutoAnalyze(){',
                        '// Read-only historical mode:')
        self.assertIn("gfAutoLocalOnly='1'", local)
        self.assertIn("const externalOptIn=!automaticLocal&&", local)
        self.assertIn("'/api/agent/evidence/'+expected", local)
        self.assertIn("'X-GeoField-LLM-Opt-In':'1'", local)
        paid = section(SERVER, "if path.startswith('/api/agent/evidence/'):",
                       "if path.startswith('/api/integration/decision/'):")
        self.assertIn("self.headers.get('X-GeoField-LLM-Opt-In')=='1'", paid)
        self.assertIn("gf_agent_llm_config()['configured']", paid)
        self.assertLess(paid.index('gf_paid_ai_preflight('),
                        paid.index('gf_agent_llm_optional(response,opt_in=True)'))
        opt = section(SERVER, 'def gf_agent_llm_optional(', 'def gf_agent_evaluate(')
        self.assertIn('if not opt_in:', opt)

    def test_fea_provenance_and_report_source_checks_remain_intact(self):
        server = section(SERVER, 'def gf_current_verified_report(', 'def r128_r12_status(')
        self.assertIn('reverify_task_for_display(', server)
        self.assertIn('gf_verified_analysis_report_ready(', server)
        self.assertIn('append_verified_evidence(', server)
        html = section(JS, 'async function gfBuildVisibleReport(', '// GEOFIELD_')
        self.assertIn('/api/results/report/', html)
        self.assertIn('gfVerifyFeaHtmlNumericReadback(', html)
        self.assertIn('gfRequireCompletePaidReportEvidence(', html)
        self.assertLess(html.index('gfVerifyFeaHtmlNumericReadback('),
                        html.index('gfRequireCompletePaidReportEvidence('))

    def test_oneclick_mesh_and_report_are_explicitly_chained(self):
        oneclick = section(JS, "$('feaRunBtn').onclick=async()=>{",
                           '// Read-only historical mode:')
        self.assertIn('gfAutoStage2Verification(', oneclick)
        self.assertIn('gfStage3CompleteReport(', oneclick)
        self.assertIn('gfStage4CompareWithPast()', oneclick)
        self.assertIn('gfReportSelectionCurrent(', oneclick)

    def test_gaps_are_documented_without_falsely_certifying_completion(self):
        for key in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6',
                    '유료', '원본', '미완료', '로컬'):
            self.assertIn(key, DOCUMENT)
        # Diagnostic-only. Explicitly do not assert known gaps as
        # "fixed"; later development will modify these code paths.
        report = section(JS, 'async function gfStage3CompleteReport(',
                         'let gfOneClickPreparing=')
        off = 'gfBuildVisibleReport(uid,sha,run,caseSha,false,requireMesh)' in report
        local = section(JS, 'function gfMaybeAutoAnalyze(){',
                        "// Read-only evidence-based agent;")
        requires_tab = "active!=='integration'" in local
        print('PIPELINE_SOURCE_AUDIT:', {
            'CAD_to_BrepMFR_R12_auto_paths_present': True,
            'FEA_three_mesh_and_integrated_HTML_chained': True,
            'local_agent_automatic_path_limited_to_integration_tab': requires_tab,
            'automatic_report_forces_ai_OFF_including_local_rules': off,
            'paid_provider_requires_explicit_optin': True,
            'ML_uncertainty_to_agent_handoff_completed': 'NOT_ESTABLISHED',
            'actual_Windows_UI_and_paid_API_verified': False,
        })


if __name__ == '__main__':
    unittest.main()
