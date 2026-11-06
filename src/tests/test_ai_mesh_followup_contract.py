"""Extract native optional AI follow-up logic: no solver, SQLite, secrets or network."""
import ast
import json
import re
import threading
from pathlib import Path
import unittest

SOURCE=(Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py").read_text(encoding="utf8")
TREE=ast.parse(SOURCE)
NAMES={"gf_ai_verified_mesh_followup","gf_agent_llm_optional"}
FUNCS=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
assert {n.name for n in FUNCS}==NAMES
SCOPE={}
exec(compile(ast.fix_missing_locations(ast.Module(body=FUNCS,type_ignores=[])),
             "GeoField_CAD_Analysis.py","exec"),SCOPE)

UID="1"*32
STUDY="2"*32
SHA="a"*64
CASE="b"*64
BASE_RUN="7"*32
BASE={"cad_sha256":SHA,"case_sha256":CASE}
CASES=[{"case_sha256":str(i)*64} for i in (3,4,5)]
ROWS=[{"cad_sha256":SHA,"mesh_target_mm":2.0-i*0.5,
       "max_stress_mpa":15.+i,"max_displacement_mm":0.02+i*.001}
      for i in range(3)]
ANALYSIS={
 "status":"verified_three_mesh_sensitivity_only","same_physical_case":True,
 "solver_evidence":"each_calculix_run_revalidated",
 "convergence_certified":False,"safety_certified":False,
 "runs_coarse_to_fine":ROWS,
 "adjacent_changes":[{"stress_relative_change_percent":3.0,
                      "displacement_relative_change_percent":2.5} for _ in range(2)],
 "actual_mesh_resolution_diagnostic":{"effective_mean_edge_refinement":True},
 "actual_load_moment_diagnostic":{"mesh_only_attribution_supported_by_this_screen":True},
 "numeric_stability_diagnostic":{"passes":True}}
PRIVATE={"id":STUDY,"cad_job_id":UID,"cad_sha256":SHA,"status":"complete",
         "base_run_id":BASE_RUN,"base_case_sha256":CASE}
# Real completed studies no longer have their temporary cases in RAM.
SCOPE.update({
    "valid_uid":lambda v:isinstance(v,str) and re.fullmatch("[0-9a-f]{32}",v) is not None,
    "STATE_LOCK":threading.RLock(),
    "MESH_STUDIES":{STUDY:PRIVATE},
    "mesh_cases":lambda base:CASES if base.get("case_sha256")==CASE else
                   [{"case_sha256":"f"*64} for _ in range(3)],
    "r1213_mesh_series_verified_public":lambda study:{
        "mesh_study_verified":True,"status":"complete",
        "base_fea_binding_verified":True,"base_run_id":BASE_RUN,
        "base_case_sha256":CASE,"study_analysis":ANALYSIS},
    "gf_agent_llm_config":lambda env:{"configured":True,"provider":"deepseek",
                  "selected_model":"deepseek-flash","timeout_seconds":60}
})

class AIFollowupTests(unittest.TestCase):
    def test_independently_verified_three_mesh_stats(self):
        summary=SCOPE["gf_ai_verified_mesh_followup"](STUDY,UID,SHA,BASE,BASE_RUN)
        self.assertIsNotNone(summary)
        self.assertEqual(len(summary["runs_coarse_to_fine"]),3)
        self.assertEqual(summary["runs_coarse_to_fine"][0]["max_stress_mpa"],15.0)
        self.assertEqual(len(summary["adjacent_relative_change_percent"]),2)
        self.assertFalse(summary["design_improvement_verified"])
        self.assertFalse(summary["convergence_certified"])
        self.assertFalse(summary["safety_certified"])

    def test_stale_identity_or_failed_solver_is_never_evidence(self):
        call=SCOPE["gf_ai_verified_mesh_followup"]
        for args in ((STUDY,UID,"f"*64,BASE,BASE_RUN),
                     (STUDY,UID,SHA,{**BASE,"case_sha256":"f"*64},BASE_RUN),
                     ("f"*32,UID,SHA,BASE,BASE_RUN),
                     (STUDY,"0"*32,SHA,BASE,BASE_RUN)):
            with self.subTest(args=args):
                self.assertIsNone(call(*args))
        previous=SCOPE["r1213_mesh_series_verified_public"]
        try:
            SCOPE["r1213_mesh_series_verified_public"]=lambda study:{
                "mesh_study_verified":False,"status":"verification_failed","study_analysis":None}
            self.assertIsNone(call(STUDY,UID,SHA,BASE,BASE_RUN))
        finally:
            SCOPE["r1213_mesh_series_verified_public"]=previous

    def test_optin_provider_only_receives_numeric_trends(self):
        summary=SCOPE["gf_ai_verified_mesh_followup"](STUDY,UID,SHA,BASE,BASE_RUN)
        evidence={"schema":"geofield-evidence-agent-v1",
                  "cad_sha256":SHA,
                  "cad":{"findings_count":4},
                  "ml":{"status":"research_unverified"},
                  "fea":{"status":"INP_STA_FRD_reverified",
                         "maximum_von_mises_mpa":16.,
                         "maximum_displacement_mm":.03,
                         "element_type":"C3D4"},
                  "mesh_followup_context":summary}
        outbound=[]
        def request(payload,key):
            outbound.append(payload)
            self.assertEqual(key,"local-mock-secret")
            return {"choices":[{"finish_reason":"stop",
                     "message":{"content":"실제 3회 FEA 변화율 확인. 설계 변경 미실시."}}]}
        env={"DEEPSEEK_API_KEY":"local-mock-secret"}
        off=SCOPE["gf_agent_llm_optional"](evidence,opt_in=False,
                                           environ=env,transport=request)
        self.assertFalse(off["executed"])
        self.assertEqual(outbound,[])
        on=SCOPE["gf_agent_llm_optional"](evidence,opt_in=True,
                                          environ=env,transport=request)
        self.assertTrue(on["connected"])
        self.assertEqual(len(outbound),1)
        values=json.loads(outbound[0]["messages"][1]["content"])
        proof=values["verified_mesh_followup"]
        self.assertEqual(len(proof["runs_coarse_to_fine"]),3)
        self.assertFalse(proof["design_improvement_verified"])
        self.assertFalse(proof["convergence_certified"])
        self.assertFalse(proof["safety_certified"])
        self.assertIn("SAME-GEOMETRY mesh study",outbound[0]["messages"][0]["content"])
        raw=json.dumps(outbound[0])
        for forbidden in (UID,STUDY,SHA,CASE,"local-mock-secret","case_sha256",
                          "snapshot_id","run_id","face_ids"):
            self.assertNotIn(forbidden,raw)

    def test_without_verified_study_no_payload_to_ai(self):
        evidence={"schema":"geofield-evidence-agent-v1",
                  "cad":{"findings_count":0},"ml":{"status":"not_run"},
                  "fea":{"status":"not_verified"},"mesh_followup_context":None}
        seen=[]
        SCOPE["gf_agent_llm_optional"](evidence,opt_in=True,
              environ={"DEEPSEEK_API_KEY":"test"},transport=lambda p,k:(
                  seen.append(p) or {"choices":[{"finish_reason":"stop",
                  "message":{"content":"미검증"}}]}))
        self.assertNotIn("verified_mesh_followup",
                         json.loads(seen[0]["messages"][1]["content"]))

if __name__=="__main__":unittest.main()
