"""GeoField evidence AI-agent gate with real production function, synthetic evidence.

This test NEVER runs a solver, downloads a model, alters user files, or claims
real-world safety/convergence. Exact original CAD/ML/FEA values are not changed.
"""
from __future__ import annotations
import ast
import copy
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
functions=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in
           {"gf_agent_evaluate","gf_agent_validate_inputs"}]
assert len(functions)==2, "Production agent and input contract functions missing"
env={}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(SOURCE),"exec"),env)
agent=env["gf_agent_evaluate"]
CAD="a"*64;CASE="b"*64;RUN="1"*32;JOB="2"*32
def record():
    result={"schema":"geofield-fea-result-v1","status":"solver_executed_result_parsed",
            "cad_sha256":CAD,"case_sha256":CASE,
            "mesh":{"node_count":2798,"tetrahedron_count":8611,"element_type":"C3D4"},
            "results":{"maximum_nodal_von_mises_mpa":14.512,"maximum_displacement_mm":0.05698}}
    summ={"cad":{"sha256":CAD},"ml":{"state":"not_run"},"fea":{
          "state":"complete","result_run_id":RUN,"result_case_sha256":CASE,
          "maximum_von_mises_mpa":14.512,"maximum_displacement_mm":0.05698,
          "node_count":2798,"tetrahedron_count":8611},
          "fea_case_provenance":{"verified_mesh":{"nodes":2798,"tetrahedra":8611},
            "source_verification":"INP_STA_FRD_reverified",
            "verified_run_id":RUN,"solved_case_sha256":CASE,
            "summary_numbers_crosschecked":True,
            "result_matches_selected":True,"result_matches_saved":True}}
    decision={"cad_sha256":CAD,"cad_job_id":JOB,"items":[{
              "where":"원통형 홀 후보","measured_evidence":"내경 5.5 mm (CAD 형상)",
              "face_ids":[6],"next_check":"홀 부근 실제 해석장 확인"}]}
    ml={"id":"3"*32,"cad_job_id":JOB,"cad_sha256":CAD,"status":"complete",
        "result":{"sha256":CAD,"decision_usage":"blocked_diagnostic_only",
                  "variants":{"topology_trimmed":{"faces":[
                    {"face_ordinal":6,"model_class":"blind_hole",
                     "model_score_uncalibrated":0.8}]}}}}
    task={"id":RUN,"cad_job_id":JOB,"cad_sha256":CAD,"case_sha256":CASE,
          "status":"complete","source_validation":"INP_STA_FRD_reverified","result":result}
    r12={"state":"complete","mode":"research_only","fea_calculated":False,
         "run_id":"4"*32,"cad_sha256":CAD,"candidate_count":2}
    return summ,decision,ml,r12,task

class AgentEvidenceTests(unittest.TestCase):
    def make(self):
        args=record()
        copies=copy.deepcopy(args)
        out=agent(*args)
        self.assertEqual(args,copies,"Evidence agent MUST NOT mutate caller input")
        return out
    def test_actual_reverified_run_copy_and_c3d4(self):
        out=self.make()
        self.assertEqual(out["schema"],"geofield-evidence-agent-v1")
        self.assertEqual(out["mode"],"rules_only")
        self.assertFalse(out["llm"]["connected"])
        self.assertFalse(out["llm"]["executed"])
        self.assertEqual(out["fea"]["run_id"],RUN)
        self.assertEqual(out["fea"]["case_sha256"],CASE)
        self.assertEqual(out["fea"]["maximum_von_mises_mpa"],14.512)
        self.assertEqual(out["fea"]["maximum_displacement_mm"],0.05698)
        self.assertEqual(out["fea"]["element_type"],"C3D4")
        self.assertFalse(out["fea"]["safety_certified"])
        self.assertEqual(out["fea"]["convergence"],"not_independently_verified")
        self.assertFalse(out["persisted_report"])
        self.assertTrue(any(x["kind"]=="cad" for x in out["findings"]))
        self.assertTrue(any(x["kind"]=="ml" for x in out["findings"]))
    def test_no_real_fea_blocks_all_stress_disp_numbers(self):
        s,d,m,r,t=record()
        s["fea"]={"state":"not_run"}
        t={}
        o=agent(s,d,m,r,t)
        self.assertIsNone(o["fea"]["maximum_von_mises_mpa"])
        self.assertIsNone(o["fea"]["maximum_displacement_mm"])
        self.assertIsNone(o["fea"]["run_id"])
        self.assertTrue(any(x["level"]=="blocked" and x["kind"]=="fea" for x in o["findings"]))
    def test_wrong_solver_run_id_blocks_output(self):
        s,d,m,r,t=record()
        t["id"]="9"*32
        self.assertEqual(agent(s,d,m,r,t)["fea"]["status"],"not_verified")
    def test_wrong_solver_case_blocks_output(self):
        s,d,m,r,t=record()
        t["result"]["case_sha256"]="c"*64
        self.assertEqual(agent(s,d,m,r,t)["fea"]["status"],"not_verified")
    def test_wrong_cad_sha_blocks_output(self):
        s,d,m,r,t=record()
        t["result"]["cad_sha256"]="c"*64
        self.assertEqual(agent(s,d,m,r,t)["fea"]["status"],"not_verified")
    def test_changed_numeric_value_rejected_instead_of_recomputed(self):
        s,d,m,r,t=record()
        s["fea"]["maximum_von_mises_mpa"]=999
        o=agent(s,d,m,r,t)
        self.assertEqual(o["fea"]["status"],"not_verified")
        self.assertIsNone(o["fea"]["maximum_von_mises_mpa"])
    def test_unverified_task_source_never_accepted(self):
        s,d,m,r,t=record()
        del t["source_validation"]
        self.assertEqual(agent(s,d,m,r,t)["fea"]["status"],"not_verified")
    def test_no_summary_crosscheck_rejects_fake_frd(self):
        s,d,m,r,t=record()
        s["fea_case_provenance"]["summary_numbers_crosschecked"]=False
        self.assertEqual(agent(s,d,m,r,t)["fea"]["status"],"not_verified")
    def test_stale_saved_case_is_visible_warning_not_new_solve(self):
        s,d,m,r,t=record()
        s["fea_case_provenance"]["result_matches_selected"]=False
        o=agent(s,d,m,r,t)
        self.assertEqual(o["fea"]["status"],"INP_STA_FRD_reverified")
        self.assertTrue(any("선택·저장 조건" in x["title"] for x in o["findings"]))
    def test_c3d10_only_when_explicitly_in_verified_mesh(self):
        s,d,m,r,t=record()
        t["result"]["mesh"]["element_type"]="C3D10"
        self.assertEqual(agent(s,d,m,r,t)["fea"]["element_type"],"C3D10")
    def test_unspecified_or_invalid_element_is_not_assumed_c3d4(self):
        for token in (None,"C3D4 + C3D10","TET10",5):
            with self.subTest(token=token):
                s,d,m,r,t=record()
                t["result"]["mesh"]["element_type"]=token
                self.assertEqual(agent(s,d,m,r,t)["fea"]["element_type"],"unverified")
    def test_research_ml_cannot_change_real_fea_values(self):
        s,d,m,r,t=record()
        m["result"]["variants"]["topology_trimmed"]["faces"][0]["model_class"]="dangerous_guess"
        o=agent(s,d,m,r,t)
        self.assertEqual(o["fea"]["maximum_von_mises_mpa"],14.512)
        self.assertEqual(o["ml"]["status"],"research_unverified")
        self.assertFalse(o["ml"]["used_for_structural_decision"])
    def test_stale_ml_cad_is_rejected_without_modifying_fea(self):
        s,d,m,r,t=record();m["cad_sha256"]="e"*64
        o=agent(s,d,m,r,t)
        self.assertEqual(o["ml"]["status"],"identity_rejected")
        self.assertEqual(o["fea"]["run_id"],RUN)
    def test_broken_ml_result_is_rejected_without_crashing_cad_fea(self):
        s,d,m,r,t=record();m["result"]={"sha256":CAD,"decision_usage":"something_else"}
        o=agent(s,d,m,r,t)
        self.assertEqual(o["ml"]["status"],"evidence_rejected")
        self.assertEqual(o["fea"]["status"],"INP_STA_FRD_reverified")
    def test_malformed_ml_faces_do_not_crash(self):
        s,d,m,r,t=record();m["result"]["variants"]["topology_trimmed"]="not-a-dict"
        o=agent(s,d,m,r,t)
        self.assertIsNone(o["ml"]["candidate_count"])
        self.assertEqual(o["fea"]["run_id"],RUN)
    def test_mismatched_rule_decision_cad_blocks_whole_review(self):
        s,d,m,r,t=record();d["cad_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"CAD 판단 근거"):
            agent(s,d,m,r,t)
    def test_llm_connection_always_disabled_without_provider(self):
        s,d,m,r,t=record()
        out=agent(s,d,m,r,t)
        self.assertEqual(out["llm"],{"connected":False,"executed":False,"provider":None})
        self.assertTrue(any(x["kind"]=="limitations" for x in out["findings"]))
    def test_no_model_files_or_sqlite_are_needed(self):
        s,d,m,r,t=record()
        with self.assertRaisesRegex(ValueError,"CAD 원본 식별값"):
            agent({"cad":{"sha256":"unknown"}},d,m,r,t)

if __name__=="__main__":
    unittest.main()
