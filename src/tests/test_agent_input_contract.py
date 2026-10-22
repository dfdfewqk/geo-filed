"""Versioned production AI-agent input-contract tests (synthetic data only).

Actual CAD/ML/FEA/LLM execution is not emulated; the production validator
accepts only identity-bound records and never changes caller input.
"""
import copy
import unittest
from test_agent_evidence import record, env, CAD, CASE, RUN, JOB

validate=env["gf_agent_validate_inputs"]
evaluate=env["gf_agent_evaluate"]

class AgentInputContractTests(unittest.TestCase):
    def test_versioned_contract_with_all_sources(self):
        data=record(); before=copy.deepcopy(data)
        out=validate(*data)
        self.assertEqual(data,before)
        self.assertEqual(out["schema"],"geofield-agent-input-contract-v1")
        self.assertEqual(out["cad"],{"status":"identity_verified","job_id":JOB,"sha256":CAD})
        self.assertEqual(out["ml"]["status"],"research_unverified")
        self.assertEqual(out["r12"]["status"],"research_complete")
        self.assertEqual(out["fea"]["status"],"candidate_needs_frd_verification")
        self.assertFalse(out["ml"]["structural_authority"])
        self.assertFalse(out["r12"]["structural_authority"])
        self.assertFalse(out["llm"]["connected"])
        self.assertEqual(evaluate(*data)["input_contract"]["fea"]["status"],
                         "INP_STA_FRD_reverified")

    def test_missing_current_cad_job_id_denied(self):
        s,d,m,r,t=record();d.pop("cad_job_id")
        with self.assertRaisesRegex(ValueError,"CAD 작업 ID"):
            evaluate(s,d,m,r,t)

    def test_non_hex_job_id_denied(self):
        s,d,m,r,t=record();d["cad_job_id"]="X"*32
        with self.assertRaises(ValueError):
            validate(s,d,m,r,t)

    def test_current_summary_job_mismatch_denied(self):
        s,d,m,r,t=record();s["cad_job_id"]="9"*32
        with self.assertRaisesRegex(ValueError,"작업 ID"):
            evaluate(s,d,m,r,t)

    def test_decision_sha_mismatch_denied(self):
        s,d,m,r,t=record();d["cad_sha256"]="c"*64
        with self.assertRaisesRegex(ValueError,"CAD 판단"):
            evaluate(s,d,m,r,t)

    def test_malformed_decision_list_denied(self):
        s,d,m,r,t=record();d["items"]={"bad":"items"}
        with self.assertRaisesRegex(ValueError,"근거 형식"):
            validate(s,d,m,r,t)

    def test_absent_optional_sources_explicitly_not_run(self):
        s,d,m,r,t=record()
        x=validate(s,d,None,None,None)
        self.assertEqual(x["ml"]["status"],"not_run")
        self.assertEqual(x["r12"]["status"],"not_run")
        self.assertEqual(x["fea"]["status"],"not_run")
        response=evaluate(s,d,None,None,None)
        self.assertIsNone(response["fea"]["maximum_von_mises_mpa"])

    def test_ml_other_job_blocked_not_silently_ignored(self):
        s,d,m,r,t=record();m["cad_job_id"]="f"*32
        result=evaluate(s,d,m,r,t)
        self.assertEqual(result["ml"]["status"],"identity_rejected")
        self.assertTrue(any(v["kind"]=="ml" and v["level"]=="blocked" for v in result["findings"]))
        self.assertEqual(result["fea"]["run_id"],RUN)

    def test_ml_other_step_sha_blocked(self):
        s,d,m,r,t=record();m["cad_sha256"]="f"*64
        self.assertEqual(validate(s,d,m,r,t)["ml"]["status"],"identity_rejected")

    def test_ml_stale_run_id_blocked(self):
        s,d,m,r,t=record();m["id"]="bad"
        self.assertEqual(validate(s,d,m,r,t)["ml"]["status"],"evidence_rejected")

    def test_ml_output_sha_mismatch_blocked(self):
        s,d,m,r,t=record();m["result"]["sha256"]="f"*64
        self.assertEqual(validate(s,d,m,r,t)["ml"]["status"],"evidence_rejected")

    def test_ml_output_incorrect_decision_usage_blocked(self):
        s,d,m,r,t=record();m["result"]["decision_usage"]="structural_certified"
        self.assertEqual(validate(s,d,m,r,t)["ml"]["status"],"evidence_rejected")
        self.assertFalse(evaluate(s,d,m,r,t)["ml"]["used_for_structural_decision"])

    def test_ml_candidates_wrong_type_rejected(self):
        s,d,m,r,t=record();m["result"]["variants"]["topology_trimmed"]["faces"]="garbled"
        self.assertEqual(validate(s,d,m,r,t)["ml"]["status"],"evidence_rejected")
        self.assertEqual(evaluate(s,d,m,r,t)["fea"]["run_id"],RUN)

    def test_ml_research_failure_is_distinct(self):
        s,d,m,r,t=record();m["status"]="failed"
        self.assertEqual(evaluate(s,d,m,r,t)["ml"]["status"],"failed")

    def test_r12_other_step_sha_rejected(self):
        s,d,m,r,t=record();r["cad_sha256"]="f"*64
        out=evaluate(s,d,m,r,t)
        self.assertEqual(out["input_contract"]["r12"]["status"],"identity_rejected")
        self.assertTrue(any(x["kind"]=="ml" and x["level"]=="blocked" for x in out["findings"]))
        self.assertEqual(out["fea"]["run_id"],RUN)

    def test_r12_wrong_mode_rejected(self):
        s,d,m,r,t=record();r["mode"]="structural_authority"
        self.assertEqual(validate(s,d,m,r,t)["r12"]["status"],"evidence_rejected")

    def test_r12_claims_fake_fea_calculated_rejected(self):
        s,d,m,r,t=record();r["fea_calculated"]=True
        self.assertEqual(validate(s,d,m,r,t)["r12"]["status"],"evidence_rejected")

    def test_r12_missing_run_identifier_rejected(self):
        s,d,m,r,t=record();r.pop("run_id")
        self.assertEqual(validate(s,d,m,r,t)["r12"]["status"],"evidence_rejected")

    def test_r12_boolean_count_rejected(self):
        s,d,m,r,t=record();r["candidate_count"]=True
        self.assertEqual(validate(s,d,m,r,t)["r12"]["status"],"evidence_rejected")

    def test_fea_other_cad_job_denies_all_numbers(self):
        s,d,m,r,t=record();t["cad_job_id"]="f"*32
        x=evaluate(s,d,m,r,t)
        self.assertEqual(x["fea"]["status"],"not_verified")
        self.assertIsNone(x["fea"]["maximum_von_mises_mpa"])
        self.assertEqual(x["input_contract"]["fea"]["status"],"identity_rejected")

    def test_fea_other_cad_sha_denies_numbers(self):
        s,d,m,r,t=record();t["cad_sha256"]="f"*64
        self.assertIsNone(evaluate(s,d,m,r,t)["fea"]["maximum_displacement_mm"])

    def test_fea_verified_mesh_counter_mismatch_denies_numbers(self):
        s,d,m,r,t=record();s["fea_case_provenance"]["verified_mesh"]["nodes"]=123
        x=evaluate(s,d,m,r,t)
        self.assertIsNone(x["fea"]["run_id"])
        self.assertEqual(x["fea"]["status"],"not_verified")

    def test_fea_verified_mesh_missing_denies_numbers(self):
        s,d,m,r,t=record();s["fea_case_provenance"].pop("verified_mesh")
        self.assertIsNone(evaluate(s,d,m,r,t)["fea"]["maximum_von_mises_mpa"])

    def test_fea_pending_is_not_a_solved_result(self):
        s,d,m,r,t=record();t["status"]="running"
        x=evaluate(s,d,m,r,t)
        self.assertEqual(x["fea"]["status"],"not_verified")
        self.assertEqual(x["input_contract"]["fea"]["status"],"running")

    def test_never_mutates_caller_data_when_ml_is_broken(self):
        data=record();data[2]["result"]={"variants":"wrong"}
        old=copy.deepcopy(data)
        out=evaluate(*data)
        self.assertEqual(data,old)
        self.assertEqual(out["ml"]["status"],"evidence_rejected")
        self.assertEqual(out["fea"]["run_id"],RUN)

if __name__=="__main__":
    unittest.main()
