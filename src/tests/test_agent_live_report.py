"""Read-only current-session report: actual rule-agent output, no fake LLM."""
from __future__ import annotations
import ast
import copy
import hashlib
import html
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/"payload"/"GeoField_CAD_Analysis.py"
TEXT=SERVER.read_text(encoding="utf8")


def extract(*names,env=None):
    tree=ast.parse(TEXT)
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    if {x.name for x in nodes}!=set(names):
        raise AssertionError("report-agent production functions missing")
    scope={"STATE_LOCK":threading.RLock(),"CURRENT":{"job_id":"job"},"JOBS":{"job":{"sha256":"a"*64}}}
    if env:scope.update(env)
    module=ast.Module(body=nodes,type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),str(SERVER),"exec"),scope)
    return scope


class LiveAgentReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.render=staticmethod(extract("gf_render_live_agent_report")["gf_render_live_agent_report"])
    def base(self,verified=False):
        sha="a"*64
        summary={"cad":{"sha256":sha},"fea_case_provenance":{}}
        agent={"schema":"geofield-evidence-agent-v1","mode":"rules_only",
               "cad_sha256":sha,"persisted_report":False,
               "llm":{"connected":False,"executed":False,"provider":None},
               "fea":{"status":"not_verified"},
               "findings":[{"title":"홀<후보>","evidence":"실측 & 재검토",
                            "next_check":"응력 < 안전 아님"}]}
        if verified:
            agent["fea"]={"status":"INP_STA_FRD_reverified","run_id":"b"*32,
                          "case_sha256":"c"*64}
            summary["fea_case_provenance"]={
                "source_verification":"INP_STA_FRD_reverified",
                "summary_numbers_crosschecked":True,
                "verified_run_id":"b"*32,"solved_case_sha256":"c"*64}
        return summary,agent

    def test_replaces_only_stale_agent_label_and_appends_real_findings(self):
        original="<html><body><h1>기존 보고서</h1><p>AI Agent: 미연결</p></body></html>"
        summary,agent=self.base()
        before=copy.deepcopy((summary,agent))
        result=self.render(original,summary,agent)
        self.assertIn("기존 보고서",result)
        self.assertNotIn("AI Agent: 미연결",result)
        self.assertIn("규칙 기반 분석 완료",result)
        self.assertIn("보고서 생성 시 외부 API를 호출하지 않음",result)
        self.assertIn("홀&lt;후보&gt;",result)
        self.assertIn("실측 &amp; 재검토",result)
        self.assertIn("응력 &lt; 안전 아님",result)
        self.assertIn("실제 FEA 근거가 확인되지 않아",result)
        self.assertEqual((summary,agent),before)
        self.assertEqual(result.count('id="geofield-agent-report"'),1)

    def test_verified_fea_requires_exact_matching_signed_provenance(self):
        s,a=self.base(True)
        got=self.render("<html><body></body></html>",s,a)
        self.assertIn("동일 INP/STA/FRD 재검증된 계산 근거",got)
        s["fea_case_provenance"]["verified_run_id"]="d"*32
        with self.assertRaisesRegex(ValueError,"FEA 실행"):
            self.render("<html><body></body></html>",s,a)

    def test_refuses_unexecuted_or_mismatched_or_external_llm(self):
        s,a=self.base()
        for bad in (lambda x:x.update(cad_sha256="0"*64),
                    lambda x:x.update(schema="other"),
                    lambda x:x.update(mode="external"),
                    lambda x:x["llm"].update(executed=True),
                    lambda x:x.update(persisted_report=True),
                    lambda x:x.update(findings=[])):
            obj=copy.deepcopy(a)
            bad(obj)
            with self.assertRaises(ValueError):
                self.render("<html><body></body></html>",s,obj)

    def test_escapes_hostile_html_in_real_findings(self):
        s,a=self.base()
        a["findings"][0]["title"]='<script>alert("x")</script>'
        got=self.render("<html><body>base</body></html>",s,a)
        self.assertNotIn("<script>",got)
        self.assertIn("&lt;script&gt;",got)
        self.assertIn("base",got)

    def test_existing_agent_engine_reused_no_llm_or_feasolve(self):
        expected=self.base()[1]
        saved=[]
        scope=extract("gf_current_report_agent",env={
            "review_decision":lambda *args:{"cad_sha256":"a"*64,"items":[]},
            "gf_agent_cad_features":lambda *args:{"candidates":[]},
            "gf_agent_evaluate":lambda *args,**kw:saved.append("existing_rule_agent") or expected,
            "gf_agent_restored_context":lambda *args:{"status":"not_restored"},
            "r128_r12_status":lambda *args:None,
            "qa_current_cad_evidence":lambda *args:True,
            "gf_agent_assert_restore_session":lambda *args:True})
        x=scope["gf_current_report_agent"](
            {"cad":{"sha256":"a"*64}},"job",
            {"sha256":"a"*64,"analysis":{},"findings":[]},
            {"mesh":{"face_ids":[]}},None,None,None,None,{"job_id":"job"})
        self.assertEqual(x,expected)
        self.assertEqual(saved,["existing_rule_agent"])
        self.assertNotIn("gf_agent_llm_optional",TEXT[TEXT.index("def gf_current_report_agent("):TEXT.index("def qa_report_provenance_note(")])
        self.assertIn("report=gf_render_live_agent_report(report,summary,agent)",TEXT)
        self.assertIn("agent=gf_current_report_agent(",TEXT)


if __name__=="__main__":
    unittest.main()
