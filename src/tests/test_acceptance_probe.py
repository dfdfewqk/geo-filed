"""One-shot Windows acceptance probe: read-only actual production logic, fake localhost.

No user CAD/FEA data, external API request or installed Windows runtime.
"""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from test_agent_evidence import agent,record,JOB,RUN,CAD,CASE

SOURCE=Path(__file__).resolve().parents[1]/"acceptance_probe.py"
spec=importlib.util.spec_from_file_location("acceptance_probe",SOURCE)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def fixture(*,restored=False):
    summary,decision,ml,r12,task=record()
    evidence=agent(summary,decision,ml,r12,task)
    current={"job_id":JOB,"pending_job_id":JOB}
    if restored:
        current["verified_restored_run_id"]=RUN
        evidence["restore_evidence"]={
            "status":"verified_restored_read_only","run_id":RUN,
            "cad_sha256":CAD,"case_sha256":CASE,"read_only":True}
    pages={
        "/api/status":{"ok":True,"version":"R20-core-stabilization",
            "current":current,
            "capabilities":{"cad_analysis":True,"fea":True,"ml_inference":False}},
        "/api/results/summary/"+JOB:summary,
        "/api/agent/evidence/"+JOB:evidence,
    }
    return pages


class AcceptanceProbeTests(unittest.TestCase):
    def check(self,pages):
        visited=[]
        def fetch(path):
            visited.append(path)
            return copy.deepcopy(pages[path])
        out=probe.assess(fetch=fetch)
        return out,visited

    def test_valid_solver_snapshot_reports_observed_not_production_approval(self):
        out,visited=self.check(fixture())
        self.assertEqual(out["server"],"observed_expected_local_backend")
        self.assertEqual(out["cad"],"matching_cad_sha_and_evidence_schema")
        self.assertEqual(out["fea"],"same_run_backend_reverified_source")
        self.assertEqual(out["ai"],"rules_evidence_observed")
        self.assertEqual(out["ml"],"research_unverified")
        self.assertEqual(out["restore"],"not_in_restored_session")
        self.assertEqual(out["verified_max_von_mises_mpa"],14.512)
        self.assertEqual(out["verified_max_displacement_mm"],.05698)
        self.assertEqual(out["element_type"],"C3D4")
        self.assertEqual(out["three_d_visual"],"NOT_VERIFIABLE_BY_THIS_PROBE")
        self.assertEqual(out["actual_solver_execution_this_session"],"NOT_VERIFIABLE_BY_THIS_PROBE")
        self.assertEqual(out["mesh_convergence"],"NOT_VERIFIED")
        self.assertFalse(out["production_release_approved"])
        self.assertEqual(len(visited),3)

    def test_no_source_identifiers_or_private_data_written(self):
        pages=fixture()
        out,_=self.check(pages)
        encoded=json.dumps(out,ensure_ascii=False)
        for secret in (CAD,CASE,RUN,JOB,"API_KEY","password","original.step"):
            self.assertNotIn(secret,encoded)

    def test_unverified_solver_does_not_become_measured(self):
        pages=fixture()
        pages["/api/agent/evidence/"+JOB]["fea"]["status"]="not_verified"
        out,_=self.check(pages)
        self.assertEqual(out["fea"],"not_verified_for_selected_cad")
        self.assertNotIn("verified_max_von_mises_mpa",out)

    def test_swapped_run_or_case_uses_same_actual_identity(self):
        for side,field,value in (
            ("agent","run_id","9"*32),("summary","result_run_id","9"*32),
            ("provenance","verified_run_id","9"*32),
            ("provenance","solved_case_sha256","c"*64)):
            with self.subTest(side=side,field=field):
                pages=fixture()
                if side=="agent":pages["/api/agent/evidence/"+JOB]["fea"][field]=value
                elif side=="summary":pages["/api/results/summary/"+JOB]["fea"][field]=value
                else:pages["/api/results/summary/"+JOB]["fea_case_provenance"][field]=value
                out,_=self.check(pages)
                self.assertEqual(out["fea"],"not_verified_for_selected_cad")

    def test_tampered_measurement_denied(self):
        for bad in (-3,float("inf"),float("nan"),False,{},17):
            with self.subTest(value=str(bad)):
                pages=fixture()
                pages["/api/agent/evidence/"+JOB]["fea"]["maximum_von_mises_mpa"]=bad
                out,_=self.check(pages)
                self.assertEqual(out["fea"],"not_verified_for_selected_cad")

    def test_restored_history_is_only_claimed_if_exact_run(self):
        pages=fixture(restored=True)
        out,_=self.check(pages)
        self.assertEqual(out["restore"],"verified_read_only_past_run")
        pages["/api/agent/evidence/"+JOB]["restore_evidence"]["run_id"]="9"*32
        out,_=self.check(pages)
        self.assertEqual(out["restore"],"not_verified")

    def test_malformed_optional_metadata_isolated(self):
        pages=fixture()
        pages["/api/agent/evidence/"+JOB]["fea"]=[1,2,3]
        pages["/api/results/summary/"+JOB]["fea"]=None
        pages["/api/results/summary/"+JOB]["fea_case_provenance"]="bad"
        out,_=self.check(pages)
        self.assertEqual(out["fea"],"not_verified_for_selected_cad")
        self.assertEqual(out["ai"],"unexpected_ai_contract")

    def test_other_local_server_and_no_selected_cad_are_not_success(self):
        pages=fixture()
        pages["/api/status"]["version"]="unexpected"
        out,visited=self.check(pages)
        self.assertEqual(out["server"],"unexpected_local_backend")
        self.assertEqual(visited,["/api/status"])
        pages=fixture();pages["/api/status"]["current"]={}
        out,visited=self.check(pages)
        self.assertEqual(out["cad"],"no_stable_selected_cad")
        self.assertEqual(visited,["/api/status"])

    def test_api_error_suppresses_private_exception_text(self):
        def fetch(_):raise RuntimeError("customer-secret-token data original STEP")
        # Real GET failures are OSError/ValueError types; assert sanitized errors.
        def blocked(_):raise OSError("C:/Users/Private/my-part.step")
        out=probe.assess(fetch=blocked)
        encoded=json.dumps(out)
        self.assertNotIn("Private",encoded)
        self.assertEqual(out["api_errors"][0]["error_type"],"OSError")

    def test_no_external_hosts_or_external_api_fields(self):
        import re
        source=SOURCE.read_text(encoding="utf8")
        self.assertIn('SERVER="http://127.0.0.1:8600"',source)
        self.assertIn('urllib.request.ProxyHandler({})',source)
        self.assertNotIn("https://",source)
        self.assertNotIn("X-GeoField-LLM-Opt-In",source)
        self.assertIn("production_release_approved",source)
        with self.assertRaises(ValueError):
            probe.fetch_json("https://example.invalid/api/status")

    def test_no_python_object_or_fea_payload_leaks_into_report(self):
        pages=fixture(); pages["/api/results/summary/"+JOB]["original_step"]="user-private-part.step"
        pages["/api/agent/evidence/"+JOB]["llm"]["api_key"]="never-leak-this"
        out,_=self.check(pages)
        text=json.dumps(out)
        self.assertNotIn("user-private-part",text)
        self.assertNotIn("never-leak",text)

if __name__=="__main__":unittest.main()
