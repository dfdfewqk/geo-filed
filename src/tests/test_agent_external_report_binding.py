"""Opt-in external AI report is never paid, stale or unsafe by accident.

Pure extraction of production formatter: no HTTP, model, STEP, SQLite or solver.
"""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf8"))
fn=next(x for x in TREE.body if isinstance(x,ast.FunctionDef)
        and x.name=="gf_external_report_section")
scope={}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),scope)
attach=scope["gf_external_report_section"]
SHA="a"*64
RUN="b"*32
CASE="c"*64
JOB="d"*32

def summary():
    return {
      "cad":{"sha256":SHA},
      "fea":{"state":"complete"},
      "fea_case_provenance":{"source_verification":"INP_STA_FRD_reverified",
            "summary_numbers_crosschecked":True,"verified_run_id":RUN,
            "solved_case_sha256":CASE}
    }

def approved():
    return {"cad_job_id":JOB,"cad_sha256":SHA,"run_id":RUN,
            "case_sha256":CASE,"provider":"deepseek",
            "explanation":"응력 범위 확인. <script>danger()</script>",
            "source":"explicit_one_time_consent"}

class ExternalReportBindingTests(unittest.TestCase):
    def test_actual_opt_in_response_appended_and_escaped(self):
        result=attach("<html><body>verified</body></html>",summary(),JOB,approved())
        self.assertIn("외부 AI 참고 설명",result)
        self.assertIn("DeepSeek".lower(),result.lower())
        self.assertIn("&lt;script&gt;danger()&lt;/script&gt;",result)
        self.assertNotIn("<script>",result)
        self.assertIn("API를 다시 호출하지 않음",result)

    def test_no_consent_no_append(self):
        result="<body>local only</body>"
        for data in ({},None,{**approved(),"source":"background_auto"}):
            with self.subTest(data=data):
                self.assertEqual(attach(result,summary(),JOB,data),result)

    def test_stale_cad_run_case_job_are_rejected(self):
        result="<body>local only</body>"
        for key,val in (("cad_job_id","0"*32),("cad_sha256","f"*64),
                        ("run_id","f"*32),("case_sha256","f"*64)):
            with self.subTest(field=key):
                self.assertEqual(attach(result,summary(),JOB,{**approved(),key:val}),result)
        corrupted=summary()
        corrupted["fea_case_provenance"]["summary_numbers_crosschecked"]=False
        self.assertEqual(attach(result,corrupted,JOB,approved()),result)
        corrupted=summary()
        corrupted["fea_case_provenance"]["verified_run_id"]="e"*32
        self.assertEqual(attach(result,corrupted,JOB,approved()),result)

    def test_bad_status_content_never_embedded(self):
        original="<body>verified FEA</body>"
        for description in ("", "a"*1601, "bad\x00text"):
            with self.subTest(data=description):
                self.assertEqual(attach(original,summary(),JOB,
                                        {**approved(),"explanation":description}),original)
        self.assertEqual(attach(original,summary(),JOB,
                        {**approved(),"provider":"unknown"}),original)

if __name__=="__main__":
    unittest.main()
