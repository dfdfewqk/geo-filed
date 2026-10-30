"""Actual HTML report-source formatter and FEA run identity gate regressions.

All evidence is synthetic. Real INP/STA/FRD is not available in this unit test.
"""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"payload"/"GeoField_CAD_Analysis.py"
SOURCE=FILE.read_text(encoding="utf8")
TREE=ast.parse(SOURCE)
WANTED={"qa_report_provenance_note","r125_reconcile_current_fea_summary"}
parts=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in WANTED]
assert len(parts)==len(WANTED)
ns={"valid_uid":lambda v:isinstance(v,str) and len(v)==32 and
                    all(x in "0123456789abcdef" for x in v)}
exec(compile(ast.Module(body=parts,type_ignores=[]),str(FILE),"exec"),ns)
format_note=ns["qa_report_provenance_note"]
reconcile=ns["r125_reconcile_current_fea_summary"]
RUN="1"*32
CAD="a"*64
CASE="b"*64
OTHER="c"*64

def proof():
    return {"source_verification":"INP_STA_FRD_reverified",
            "summary_numbers_crosschecked":True,
            "verified_run_id":RUN,
            "solved_case_sha256":CASE,
            "selected_case_sha256":CASE,
            "editable_case_sha256":CASE,
            "result_matches_selected":True,
            "result_matches_saved":True,
            "restored_record_active":False,
            "verified_mesh":{"tetrahedra":8611,"nodes":2798}}

def source():
    actual={
        "schema":"geofield-fea-result-v1",
        "status":"solver_executed_result_parsed",
        "cad_sha256":CAD,
        "case_sha256":CASE,
        "results":{"maximum_nodal_von_mises_mpa":14.5,
                   "maximum_displacement_mm":0.0569},
        "mesh":{"node_count":2798,"tetrahedron_count":8611},
    }
    task={"id":RUN,"cad_job_id":"2"*32,"cad_sha256":CAD,
          "case_sha256":CASE,"status":"complete",
          "source_validation":"INP_STA_FRD_reverified","result":actual}
    summary={"cad":{"sha256":CAD},"fea":{
        "state":"complete","maximum_von_mises_mpa":14.5,
        "maximum_displacement_mm":0.0569,
        "node_count":2798,"tetrahedron_count":8611,
        "result_run_id":RUN,"result_case_sha256":CASE}}
    return summary,task

class ReportProvenanceTests(unittest.TestCase):
    def test_same_run_mesh_and_case_are_spelled_out(self):
        msg=format_note(proof())
        self.assertIn(RUN,msg)
        self.assertIn(CASE,msg)
        self.assertIn("2798",msg)
        self.assertIn("8611",msg)
        self.assertIn("보고서를 여는 것은 새 FEA 계산이 아닙니다",msg)
        self.assertIn("현재 작업에 연결된 검증 완료 실행 결과",msg)
        self.assertNotIn("과거 저장된 실행을 검증 복원한 결과",msg)
        self.assertIn("메시 수렴",msg)
        self.assertNotIn("주의:",msg)

    def test_restored_record_disclosed_as_past_run(self):
        p=proof();p["restored_record_active"]=True
        msg=format_note(p)
        self.assertIn("과거 저장된 실행을 검증 복원한 결과",msg)
        self.assertNotIn("현재 작업에 연결된 검증 완료 실행 결과",msg)
        self.assertIn("이 보고서를 여는 것은 새 FEA 계산이 아닙니다",msg)
        self.assertIn(RUN,msg)

    def test_saved_and_selected_case_mismatch_visible(self):
        p=proof()
        p["selected_case_sha256"]=OTHER
        p["editable_case_sha256"]=OTHER
        p["result_matches_selected"]=False
        p["result_matches_saved"]=False
        msg=format_note(p)
        self.assertIn("선택된 해석 조건과 실제 계산 조건이 다릅니다",msg)
        self.assertIn("마지막 저장된 조건과 실제 계산 조건이 다릅니다",msg)
        self.assertIn(CASE,msg)
        self.assertIn(OTHER,msg)

    def test_no_unverified_run_label(self):
        for change in (
            {"summary_numbers_crosschecked":False},
            {"source_verification":"report_consistency_rejected"},
            {"verified_run_id":"not-valid"},
            {"verified_run_id":None},
        ):
            with self.subTest(change=change):
                p=proof();p.update(change)
                note=format_note(p)
                self.assertNotIn(RUN,note)
                self.assertIn("출처 확인 실패",note)

    def test_report_identifier_is_html_escaped(self):
        p=proof()
        p["verified_mesh"]["nodes"]="<script>alert(1)</script>"
        msg=format_note(p)
        self.assertNotIn("<script>",msg)
        self.assertIn("&lt;script&gt;",msg)

    def test_reconciled_actual_run_passes_without_rewriting_numbers(self):
        summary,task=source()
        p=proof()
        expected=dict(summary["fea"])
        returned=reconcile(summary,task,p,CAD)
        self.assertIs(returned,summary)
        self.assertEqual(returned["fea"],expected)
        self.assertTrue(p["summary_numbers_crosschecked"])
        self.assertIn(RUN,format_note(p))

    def test_changed_number_rejects_report_and_removes_run_identity(self):
        summary,task=source()
        summary["fea"]["maximum_von_mises_mpa"]=999
        p=proof()
        returned=reconcile(summary,task,p,CAD)
        self.assertEqual(returned["fea"]["state"],"rejected")
        self.assertNotIn("maximum_von_mises_mpa",returned["fea"])
        self.assertNotIn("result_run_id",returned["fea"])
        self.assertIsNone(p["verified_run_id"])
        self.assertIn("출처 확인 실패",format_note(p))

    def test_changed_mesh_nodes_rejects_report(self):
        summary,task=source()
        summary["fea"]["node_count"]=123
        p=proof()
        reconcile(summary,task,p,CAD)
        self.assertEqual(summary["fea"]["state"],"rejected")
        self.assertFalse(p["summary_numbers_crosschecked"])

    def test_mismatched_task_case_cannot_crosscheck(self):
        summary,task=source()
        task["result"]["case_sha256"]=OTHER
        p=proof()
        reconcile(summary,task,p,CAD)
        self.assertEqual(summary["fea"]["state"],"rejected")
        self.assertIn("출처 확인 실패",format_note(p))

if __name__=="__main__":
    unittest.main()
