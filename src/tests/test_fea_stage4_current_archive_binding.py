"""Stage 4 read-only archive identity regression without importing private CAD runtime.

Extract the production helper as AST, drive it with mock verified solver/archive
responses, and ensure stale or unarchived runs fail closed. No disk writes.
"""
import ast
import copy
import re
import threading
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "payload" / "GeoField_CAD_Analysis.py"
ROOT = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
TARGET = next((node for node in ROOT.body
               if isinstance(node, ast.FunctionDef) and node.name == "gf_oneclick_current_snapshot"), None)
if TARGET is None:
    raise RuntimeError("Production Stage-4 current-snapshot binding function missing")
FUNCTION = compile(ast.Module(body=[TARGET], type_ignores=[]), str(SOURCE), "exec")
UID = "1" * 32
RUN = "2" * 32
SNAP = "3" * 32
SHA = "a" * 64
CASE = "b" * 64


class CurrentArchiveBindingTests(unittest.TestCase):
    def make(self, *, wrong_archive=False, no_archive=False, stale=False):
        current = {"job_id": UID, "pending_job_id": None}
        job = {"id": UID, "status": "complete", "sha256": SHA}
        task = {"id": RUN, "status": "complete", "cad_job_id": UID,
                "cad_sha256": SHA, "case_sha256": CASE,
                "history_archive_status": "failed" if no_archive else "saved",
                "history_snapshot_id": SNAP}
        case = {"case_sha256": CASE, "cad_sha256": SHA}
        counts = {"solver": 0, "archive": 0}
        def valid_uid(value):
            return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None
        def verify_task(entry, uid, sha, signed_case, jobs_dir):
            counts["solver"] += 1
            self.assertEqual(entry["id"], RUN)
            self.assertEqual(uid, UID)
            self.assertEqual(sha, SHA)
            self.assertEqual(signed_case, case)
            return {**entry, "source_validation": "INP_STA_FRD_reverified"}
        def verify_snapshot(sid):
            counts["archive"] += 1
            self.assertEqual(sid, SNAP)
            if stale:
                current["job_id"] = "4" * 32
            return {"ok": True, "verification": "rechecked_actual_inp_sta_frd",
                    "snapshot_id": SNAP, "cad_job_id": UID,
                    "cad_sha256": SHA, "run_id": "5" * 32 if wrong_archive else RUN,
                    "case_sha256": CASE}
        namespace = {
            "CURRENT": current, "JOBS": {UID: job}, "FEA_JOBS": {RUN: task},
            "STATE_LOCK": threading.RLock(), "JOBS_DIR": object(),
            "valid_uid": valid_uid,
            "r181_current_result_case": lambda uid: copy.deepcopy(case),
            "qa8_verified_completed_fea_status": verify_task,
            "r184_verified_archive_numbers": verify_snapshot,
        }
        exec(FUNCTION, namespace)
        return namespace["gf_oneclick_current_snapshot"], namespace, counts

    def test_exact_active_run_is_independently_verified_and_read_only(self):
        handler, state, counts = self.make()
        before = copy.deepcopy((state["CURRENT"], state["JOBS"], state["FEA_JOBS"]))
        response = handler(UID, RUN)
        self.assertEqual(response["status"], "verified_current_fea_snapshot")
        self.assertEqual(response["snapshot_id"], SNAP)
        self.assertEqual(response["run_id"], RUN)
        self.assertEqual(response["case_sha256"], CASE)
        self.assertIs(response["archive_saved"], True)
        self.assertIs(response["read_only"], True)
        self.assertEqual(counts, {"solver": 1, "archive": 1})
        self.assertEqual((state["CURRENT"], state["JOBS"], state["FEA_JOBS"]), before)

    def test_unarchived_fea_is_rejected_before_legacy_verifier(self):
        handler, _, counts = self.make(no_archive=True)
        with self.assertRaisesRegex(ValueError, "자동 저장"):
            handler(UID, RUN)
        self.assertEqual(counts, {"solver": 0, "archive": 0})

    def test_wrong_archive_run_does_not_bind_to_current(self):
        handler, _, counts = self.make(wrong_archive=True)
        with self.assertRaisesRegex(ValueError, "식별값"):
            handler(UID, RUN)
        self.assertEqual(counts, {"solver": 1, "archive": 1})

    def test_selection_changed_mid_verification_is_rejected(self):
        handler, _, counts = self.make(stale=True)
        with self.assertRaisesRegex(ValueError, "변경"):
            handler(UID, RUN)
        self.assertEqual(counts, {"solver": 1, "archive": 1})

    def test_wrong_run_or_missing_case_cannot_be_current(self):
        handler, state, counts = self.make()
        with self.assertRaises(ValueError):
            handler(UID, "6" * 32)
        state["JOBS"][UID]["sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            handler(UID, RUN)
        self.assertEqual(counts, {"solver": 0, "archive": 0})


if __name__ == "__main__":
    unittest.main()
