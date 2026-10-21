"""CAD/session regression tests using the actual backend function AST.
No FreeCAD, CalculiX or private STEP/FRD files are required.
"""
import ast
import json
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "payload" / "GeoField_CAD_Analysis.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
TARGETS = {"qa_active_cad_job_status", "qa_bind_verified_fea_field", "r172_restore"}
NODES = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in TARGETS]
assert len(NODES) == len(TARGETS)
ENV = {"json": json, "STATE_LOCK": threading.RLock()}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(ROOT / "payload" / "GeoField_CAD_Analysis.py"), "exec"), ENV)
ENV["valid_uid"] = lambda value: isinstance(value, str) and len(value) == 32 and all(ch in "0123456789abcdef" for ch in value)
cad_status = ENV["qa_active_cad_job_status"]
restore = ENV["r172_restore"]
bind_field = ENV["qa_bind_verified_fea_field"]
OLD = "1" * 32
NEW = "2" * 32
RUN = "3" * 32
SHA = "a" * 64
CASE_SHA = "b" * 64


class ActiveCadStatusTests(unittest.TestCase):
    def test_current_completed_cad_is_returned(self):
        job = {"id": OLD, "status": "complete", "sha256": SHA}
        result = cad_status(OLD, {"job_id": OLD, "pending_job_id": OLD}, job)
        self.assertEqual(result, job)
        self.assertIsNot(result, job)

    def test_new_pending_step_blocks_old_completed_result(self):
        old = {"id": OLD, "status": "complete", "sha256": SHA}
        with self.assertRaisesRegex(ValueError, "현재 선택"):
            cad_status(OLD, {"job_id": None, "pending_job_id": NEW}, old)

    def test_old_completed_result_blocked_after_new_import_finishes(self):
        old = {"id": OLD, "status": "complete", "sha256": SHA}
        with self.assertRaises(ValueError):
            cad_status(OLD, {"job_id": NEW, "pending_job_id": NEW}, old)

    def test_active_pending_cad_can_be_polled(self):
        job = {"id": NEW, "status": "running", "sha256": SHA}
        self.assertEqual(cad_status(NEW, {"job_id": None, "pending_job_id": NEW}, job), job)

    def test_wrong_job_identity_and_malformed_id_are_rejected(self):
        with self.assertRaises(ValueError):
            cad_status(OLD, {"pending_job_id": OLD}, {"id": NEW, "status": "complete"})
        with self.assertRaises(ValueError):
            cad_status("../../history", {"job_id": "../../history"}, {})


class FEARecoveryRaceTests(unittest.TestCase):
    def setUp(self):
        ENV["CURRENT"] = {"job_id": OLD, "pending_job_id": OLD}
        ENV["JOBS"] = {}
        ENV["FEA_JOBS"] = {}
        ENV["JOBS_DIR"] = Path("/nonexistent-test-only")
        ENV["rule_findings"] = lambda model: []
        self.cad = {
            "sha": SHA, "analysis": {"source": "generic.step", "sha256": SHA},
            "model": {"sha256": SHA},
            "case": {"case_sha256": CASE_SHA, "cad_sha256": SHA},
        }
        ENV["restore_payload"] = lambda *args, **kwargs: (self.cad, RUN, {"cad_sha256": SHA, "case_sha256": CASE_SHA}, None)

    def test_restore_keeps_original_behavior_for_stable_active_cad(self):
        result = restore(OLD)
        self.assertEqual(result["run_id"], RUN)
        self.assertEqual(ENV["CURRENT"]["job_id"], OLD)
        self.assertEqual(ENV["FEA_JOBS"][RUN]["case_sha256"], CASE_SHA)

    def test_new_step_started_during_frD_read_rejects_restore(self):
        def interrupted(*args, **kwargs):
            ENV["CURRENT"].update(job_id=None, pending_job_id=NEW)
            return self.cad, RUN, {"cad_sha256": SHA, "case_sha256": CASE_SHA}, None
        ENV["restore_payload"] = interrupted
        with self.assertRaisesRegex(ValueError, "활성 CAD가 변경"):
            restore(OLD)
        self.assertEqual(ENV["CURRENT"]["pending_job_id"], NEW)
        self.assertNotIn(RUN, ENV["FEA_JOBS"])

    def test_new_step_completed_during_frD_read_also_rejects_restore(self):
        def finished(*args, **kwargs):
            ENV["CURRENT"].update(job_id=NEW, pending_job_id=NEW)
            return self.cad, RUN, {"cad_sha256": SHA, "case_sha256": CASE_SHA}, None
        ENV["restore_payload"] = finished
        with self.assertRaisesRegex(ValueError, "활성 CAD가 변경"):
            restore(OLD)
        self.assertEqual(ENV["CURRENT"]["job_id"], NEW)
        self.assertNotIn(OLD, ENV["JOBS"])

    def test_mismatched_stored_cad_model_sha_fails_before_restore(self):
        self.cad["model"]["sha256"]="e"*64
        with self.assertRaisesRegex(ValueError,"SHA"):
            restore(OLD)
        self.assertEqual(ENV["CURRENT"]["job_id"],OLD)
        self.assertEqual(ENV["FEA_JOBS"],{})

    def test_mismatched_saved_cad_analysis_sha_fails_before_restore(self):
        self.cad["analysis"]["sha256"]="e"*64
        with self.assertRaisesRegex(ValueError,"SHA"):
            restore(OLD)
        self.assertEqual(ENV["CURRENT"]["job_id"],OLD)
        self.assertEqual(ENV["FEA_JOBS"],{})

    def test_read_only_preview_does_not_mutate_active_session(self):
        result = restore(OLD, include_bundle=True, commit=False)
        self.assertTrue(result["has_3d_field"] is False)
        self.assertEqual(ENV["CURRENT"]["job_id"], OLD)
        self.assertEqual(ENV["JOBS"], {})



class FEASurfaceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.field={"schema":"geofield-fea-surface-field-v1",
                    "source":"actual_calculix_ascii_frd",
                    "cad_sha256":SHA, "case_sha256":CASE_SHA,
                    "von_mises_mpa":[1., 2.], "displacements_mm":[[0.,0.,0.],[0.,0.,0.]]}

    def test_verified_surface_tag_preserves_values_and_input(self):
        before=json.dumps(self.field,sort_keys=True)
        result=bind_field(self.field,SHA,CASE_SHA,RUN,OLD)
        self.assertEqual(result["run_id"],RUN)
        self.assertEqual(result["cad_job_id"],OLD)
        self.assertEqual(result["von_mises_mpa"],[1.,2.])
        self.assertEqual(json.dumps(self.field,sort_keys=True),before)

    def test_wrong_cad_and_case_are_rejected(self):
        with self.assertRaises(ValueError):
            bind_field(self.field,"f"*64,CASE_SHA,RUN,OLD)
        with self.assertRaises(ValueError):
            bind_field(self.field,SHA,"f"*64,RUN,OLD)

    def test_old_run_tag_is_not_overwritten(self):
        self.field["run_id"]=NEW
        with self.assertRaisesRegex(ValueError,"이전 실행"):
            bind_field(self.field,SHA,CASE_SHA,RUN,OLD)

    def test_other_cad_job_id_tag_is_not_overwritten(self):
        self.field["cad_job_id"]=NEW
        with self.assertRaises(ValueError):
            bind_field(self.field,SHA,CASE_SHA,RUN,OLD)

    def test_incomplete_or_unverified_surface_is_rejected(self):
        for value in (None, {}, {**self.field,"source":"predicted_ml"},
                      {**self.field,"schema":"unknown"}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                bind_field(value,SHA,CASE_SHA,RUN,OLD)

    def test_restoration_bundle_carries_identity_tags(self):
        ENV["CURRENT"] = {"job_id": OLD, "pending_job_id": OLD}
        ENV["JOBS"]={};ENV["FEA_JOBS"]={};ENV["JOBS_DIR"]=Path("/nonexistent-test-only")
        ENV["rule_findings"]=lambda model:[]
        cad={"sha":SHA,"analysis":{"source":"example.step","sha256":SHA},
             "model":{"sha256":SHA},
             "case":{"cad_sha256":SHA,"case_sha256":CASE_SHA}}
        source={"schema":"geofield-fea-surface-field-v1",
                "source":"actual_calculix_ascii_frd","cad_sha256":SHA,
                "case_sha256":CASE_SHA,"von_mises_mpa":[1.]}
        ENV["restore_payload"]=lambda *a,**kw:(cad,RUN,{"cad_sha256":SHA,"case_sha256":CASE_SHA},source)
        res=restore(OLD,include_bundle=True,commit=False)
        self.assertEqual(res["field"]["run_id"],RUN)
        self.assertEqual(res["field"]["cad_job_id"],OLD)
        self.assertNotIn("run_id",source)
        self.assertEqual(ENV["JOBS"],{})


class FieldEndpointGateTests(unittest.TestCase):
    def test_current_fea_field_rechecks_identity_after_disk_verification(self):
        start=SOURCE.index("if path.startswith('/api/fea/field/'):")
        end=SOURCE.index("if path.startswith('/api/fea/previous_overview/'):",start)
        block=SOURCE[start:end]
        self.assertIn("qa_bind_verified_fea_field(payload,job['sha256']",block)
        self.assertIn("CURRENT.get('job_id')==active",block)
        self.assertIn("task.get('case_sha256')",block)

if __name__ == "__main__":
    unittest.main()
