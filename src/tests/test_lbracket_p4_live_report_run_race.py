"""P4 original L-bracket: same-CAD newer FEA must invalidate old live report.

Run the actual production final-run selector as pure source with synthetic
tasks. No solver, STEP, SQLite, private runtime, paid LLM or real archive write.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import threading
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TEXT=SOURCE.read_text(encoding="utf-8")
TREE=ast.parse(TEXT)
TARGET="qa_report_active_run_unchanged"
NODE=next(x for x in TREE.body if isinstance(x,ast.FunctionDef) and x.name==TARGET)

CAD_ID="a"*32
CAD_SHA="b"*64
CASE_SHA="c"*64
RUN_A="1"*32
RUN_B="2"*32

def task(rid,status="complete",**kwargs):
    t={"id":rid,"cad_job_id":CAD_ID,"cad_sha256":CAD_SHA,
       "case_sha256":CASE_SHA,"status":status,
       "result":{"case_sha256":CASE_SHA}}
    t.update(kwargs)
    return t

class LBracketCurrentRunReportGate(unittest.TestCase):
    def setUp(self):
        self.current={"job_id":CAD_ID,"pending_job_id":CAD_ID,
                      "verified_restored_run_id":None}
        self.jobs={CAD_ID:{"status":"complete","sha256":CAD_SHA}}
        self.fea={RUN_A:task(RUN_A)}
        scope={"CURRENT":self.current,"STATE_LOCK":threading.RLock(),
               "JOBS":self.jobs,"FEA_JOBS":self.fea}
        exec(compile(ast.Module(body=[NODE],type_ignores=[]),
                     str(SOURCE),"exec"),scope)
        self.guard=scope[TARGET]

    def verify(self,run_id=RUN_A):
        return self.guard(CAD_ID,CAD_SHA,run_id,CASE_SHA)

    def test_single_verified_original_l_bracket_run_is_allowed_read_only(self):
        previous=copy.deepcopy((self.current,self.jobs,self.fea))
        self.assertTrue(self.verify())
        self.assertEqual((self.current,self.jobs,self.fea),previous)

    def test_new_run_queued_running_completed_blocks_old_html_and_export(self):
        for state in ("queued","running","complete","failed"):
            with self.subTest(state=state):
                self.fea[RUN_B]=task(RUN_B,state)
                with self.assertRaisesRegex(ValueError,"최신 FEA 실행"):
                    self.verify(RUN_A)
                if state=="complete":
                    self.assertTrue(self.verify(RUN_B))
                else:
                    with self.assertRaisesRegex(ValueError,"FEA 실행 결과"):
                        self.verify(RUN_B)
                self.fea.pop(RUN_B)

    def test_restored_older_run_remains_eligible_only_during_explicit_restore(self):
        self.fea[RUN_B]=task(RUN_B,"complete")
        self.current["verified_restored_run_id"]=RUN_A
        self.assertTrue(self.verify(RUN_A))
        with self.assertRaisesRegex(ValueError,"최신 FEA 실행"):
            self.verify(RUN_B)
        self.current["verified_restored_run_id"]=RUN_B
        with self.assertRaisesRegex(ValueError,"최신 FEA 실행"):
            self.verify(RUN_A)
        self.assertTrue(self.verify(RUN_B))

    def test_same_case_hash_cannot_hide_a_new_run(self):
        self.fea[RUN_B]=task(RUN_B)
        self.assertEqual(self.fea[RUN_A]["case_sha256"],
                         self.fea[RUN_B]["case_sha256"])
        with self.assertRaises(ValueError):
            self.verify(RUN_A)

    def test_active_step_or_while_importing_another_step_is_rejected(self):
        self.current["pending_job_id"]="f"*32
        with self.assertRaisesRegex(ValueError,"STEP 선택"):
            self.verify()
        self.current["pending_job_id"]=CAD_ID
        self.current["job_id"]="f"*32
        with self.assertRaisesRegex(ValueError,"STEP 선택"):
            self.verify()

    def test_replaced_solver_run_or_case_is_rejected(self):
        self.fea[RUN_A]["result"]["case_sha256"]="d"*64
        with self.assertRaisesRegex(ValueError,"FEA 실행 결과"):
            self.verify()
        self.fea[RUN_A]["result"]["case_sha256"]=CASE_SHA
        self.fea[RUN_A]["cad_sha256"]="e"*64
        with self.assertRaisesRegex(ValueError,"FEA 실행 결과"):
            self.verify()

    def test_both_html_preview_and_save_route_call_the_same_guard(self):
        report=next(x for x in TREE.body
                    if isinstance(x,ast.FunctionDef)
                    and x.name=="gf_current_verified_report")
        code=ast.unparse(report)
        self.assertIn("qa_report_active_run_unchanged(uid, job['sha256']",code)
        handler=next(x for x in TREE.body
                     if isinstance(x,ast.ClassDef) and x.name=="Handler")
        post=next(x for x in handler.body
                  if isinstance(x,ast.FunctionDef) and x.name=="do_POST")
        source=ast.unparse(post)
        self.assertIn("qa_report_active_run_unchanged(uid, data['cad_sha256']",source)
        section=source[source.index("if path.startswith('/api/results/report-save/'):"):]
        self.assertLess(section.index("qa_report_active_run_unchanged("),
                        section.index("saved = save_immutable_html("))


if __name__=="__main__":
    unittest.main(verbosity=2)
