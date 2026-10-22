"""Stage 5 bridge: actual selected ML/R12 job feeds the actual agent evaluator.

Runs production R12 status and research-only selector, then the agent's
production evaluator with synthetic already-reverified FEA input. No solver,
private STEP/FRD, or live GUI is simulated as having run.
"""
import ast
import copy
import threading
import unittest
from pathlib import Path

from test_agent_evidence import agent, record, CAD, CASE, RUN, JOB
from test_ml_evidence import module as ml_contract

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
real=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="r128_r12_status"]
assert len(real)==1, "Production R12 status missing"


def r12_task(id, sha=CAD, status="complete"):
    task={"id":id,"cad_job_id":JOB,"cad_sha256":sha,
          "automatic":True,"provider":"r12","status":status}
    if status=="complete":
        task["result"]={"cad_sha256":sha,"status":"research_not_for_production",
            "decision_usage":"blocked_diagnostic_only",
            "is_independent_r12_research":True,"geometry_certified":False,
            "fea_calculated":False,"candidate_count":1,"predictions":[]}
    return task


class JoinedEvidence(unittest.TestCase):
    def setUp(self):
        self.newid="6"*32
        self.oldid="5"*32
        self.brepid="4"*32
        self.job={"sha256":CAD,"status":"complete","auto_ml_enabled":True,
                  "auto_ml_run_id":self.newid}
        self.current={"job_id":JOB}
        self.r12={self.oldid:r12_task(self.oldid),
                  self.newid:r12_task(self.newid)}
        self.brep={self.brepid:{
                    "id":self.brepid,"cad_job_id":JOB,"cad_sha256":CAD,
                    "automatic":True,"status":"failed"}}
        scope={"JOBS":{JOB:self.job},"CURRENT":self.current,
               "R12_JOBS":self.r12,"STATE_LOCK":threading.RLock()}
        exec(compile(ast.Module(body=real,type_ignores=[]),str(SOURCE),"exec"),scope)
        self.state=scope["r128_r12_status"]

    def selected(self):
        result=ml_contract.select_current_task(
            JOB,CAD,self.job.get("auto_ml_run_id"),
            list(self.brep.values()),list(self.r12.values()))
        return result

    def evaluated(self):
        summary,decision,_,_,fea=record()
        original=copy.deepcopy((summary,decision,fea))
        active=self.selected()
        research=self.state(JOB,CAD) if active and active[0]=="r12" else {
            "state":"not_run","mode":"research_only","cad_sha256":CAD}
        brep=active[1] if active and active[0]=="brepmfr" else None
        result=agent(summary,decision,brep,research,fea)
        self.assertEqual((summary,decision,fea),original)
        return result

    def test_latest_successful_r12_selected_and_fea_preserved(self):
        provider,task=self.selected()
        self.assertEqual((provider,task["id"]),("r12",self.newid))
        output=self.evaluated()
        self.assertEqual(output["fea"]["status"],"INP_STA_FRD_reverified")
        self.assertEqual(output["fea"]["run_id"],RUN)
        self.assertEqual(output["fea"]["maximum_von_mises_mpa"],14.512)
        self.assertFalse(output["ml"]["used_for_structural_decision"])
        self.assertEqual(output["ml"]["r12_status"],"research_complete")

    def test_old_success_does_not_replace_current_failed_r12(self):
        self.r12[self.newid]=r12_task(self.newid,status="failed")
        output=self.evaluated()
        self.assertEqual(output["ml"]["r12_status"],"failed")
        self.assertEqual(output["fea"]["run_id"],RUN)

    def test_old_complete_r12_ignored_for_selected_brepmfr(self):
        self.job["auto_ml_run_id"]=self.brepid
        self.brep[self.brepid]["status"]="running"
        output=self.evaluated()
        self.assertEqual(output["ml"]["status"],"running")
        self.assertNotEqual(output["ml"].get("r12_status"),"research_complete")
        self.assertEqual(output["fea"]["run_id"],RUN)

    def test_missing_active_r12_never_reuses_old_record(self):
        self.job["auto_ml_run_id"]="7"*32
        self.assertIsNone(self.selected())
        self.assertEqual(self.state(JOB,CAD)["state"],"not_run")

    def test_changed_cad_blocks_r12_bridge(self):
        self.current["job_id"]="8"*32
        self.assertEqual(self.state(JOB,CAD)["state"],"identity_rejected")

    def test_tampered_r12_cannot_override_fea(self):
        self.r12[self.newid]["result"]["fea_calculated"]=True
        output=self.evaluated()
        self.assertEqual(output["ml"]["r12_status"],"evidence_rejected")
        self.assertEqual(output["fea"]["maximum_displacement_mm"],0.05698)


if __name__=="__main__":
    unittest.main()
