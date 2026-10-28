"""A03 synthetic contract tests: actual SQLite, no Gmsh/CalculiX or user files."""
import ast
import copy
import json
import sqlite3
from contextlib import closing
import threading
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fea_history_a03 import save_verified_fea_snapshot, recent_fea_page

SHA = "a"*64
CASE_A = "b"*64
CASE_B = "c"*64
UID = "1"*32
RUN_A = "2"*32
RUN_B = "3"*32
SNAP_A = "4"*32
SNAP_B = "5"*32

SOURCE = Path(__file__).resolve().parents[1] / "payload" / "GeoField_CAD_Analysis.py"
tree = ast.parse(SOURCE.read_text(encoding="utf8"))
nodes = [node for node in tree.body if isinstance(node,ast.FunctionDef)
         and node.name == "archive_current_job"]
assert len(nodes) == 1


def summary(run=RUN_A, case=CASE_A, stress=12.0):
    return {"cad":{"sha256":SHA,"name":"real-name-not-exported.step"},
            "fea":{"state":"complete","result_run_id":run,
                   "result_case_sha256":case,
                   "maximum_von_mises_mpa":stress,
                   "maximum_displacement_mm":0.015}}


class ArchiveSQLiteContract(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="geofield-a03-test-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.db = self.root/"real-test.sqlite3"
        self.protected = self.root/"protected_existing_user_file.frd"
        self.protected.write_bytes(b"REAL USER FILE MUST REMAIN UNCHANGED (test marker)")
        self.lock = threading.RLock()
        self.writes = 0
        self.snapshots = iter([SNAP_A,SNAP_B])
        with closing(sqlite3.connect(self.db)) as cx:
            cx.execute("CREATE TABLE snapshots ("
                       "id TEXT PRIMARY KEY,stage TEXT,job_id TEXT,"
                       "cad_sha256 TEXT,cad_name TEXT,created_at TEXT,"
                       "summary_json TEXT)")
    def fake_save(self, path, stage, uid, data):
        self.writes += 1
        sid = next(self.snapshots)
        with closing(sqlite3.connect(path)) as cx:
            cx.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?)",
                       (sid,stage,uid,SHA,"test-cad.step",
                        "2026-10-28T09:00:00",json.dumps(data)))
        return sid
    @staticmethod
    def fake_read(path, sid):
        with closing(sqlite3.connect(path)) as cx:
            row=cx.execute("SELECT summary_json FROM snapshots WHERE id=?",
                           (sid,)).fetchone()
        return json.loads(row[0]) if row else None
    def save(self,run=RUN_A,case=CASE_A,stress=12.0):
        return save_verified_fea_snapshot(
            self.db,UID,run,summary(run,case,stress),
            save=self.fake_save,read=self.fake_read,lock=self.lock)
    def assert_protected(self):
        self.assertEqual(self.protected.read_bytes(),
                         b"REAL USER FILE MUST REMAIN UNCHANGED (test marker)")

    def test_auto_save_two_real_run_ids_separate_and_read_after_restart(self):
        self.assertEqual(self.save(),SNAP_A)
        self.assertEqual(self.save(RUN_B,CASE_B,17.5),SNAP_B)
        reopened=self.fake_read(self.db,SNAP_A)
        self.assertEqual(reopened["fea"]["result_run_id"],RUN_A)
        self.assertEqual(self.fake_read(self.db,SNAP_B)["fea"]["result_run_id"],RUN_B)
        self.assertEqual(self.writes,2)
        self.assert_protected()

    def test_repeat_callback_is_idempotent_across_reopen(self):
        self.assertEqual(self.save(),SNAP_A)
        self.assertEqual(self.save(),SNAP_A)
        self.assertEqual(self.writes,1)
        self.assertEqual(recent_fea_page(self.db)["total"],1)

    def test_same_run_mismatched_case_does_not_create_duplicate(self):
        self.save()
        with self.assertRaisesRegex(ValueError,"서명"):
            self.save(RUN_A,CASE_B)
        self.assertEqual(self.writes,1)

    def test_same_run_changed_stress_is_rejected(self):
        self.save()
        with self.assertRaisesRegex(ValueError,"응력·변위"):
            self.save(RUN_A,CASE_A,15.0)
        self.assertEqual(self.writes,1)

    def test_corrupt_existing_snapshot_rejected_without_rewriting(self):
        self.save()
        with closing(sqlite3.connect(self.db)) as cx:
            data=self.fake_read(self.db,SNAP_A)
            data["fea"]["maximum_von_mises_mpa"]=999
            cx.execute("UPDATE snapshots SET summary_json=? WHERE id=?",
                       (json.dumps(data),SNAP_A))
        with self.assertRaisesRegex(ValueError,"응력·변위"):
            self.save()
        self.assertEqual(self.writes,1)
        self.assert_protected()

    def test_failed_save_not_mislabeled_as_complete(self):
        def broken(*_args):
            raise OSError("disk full")
        with self.assertRaisesRegex(OSError,"disk full"):
            save_verified_fea_snapshot(self.db,UID,RUN_A,summary(),
                                       save=broken,read=self.fake_read,lock=self.lock)
        self.assertEqual(recent_fea_page(self.db)["total"],0)
        self.assert_protected()

    def test_both_measured_values_mandatory(self):
        for key,value in [("maximum_von_mises_mpa",float("nan")),
                          ("maximum_displacement_mm",None),
                          ("maximum_von_mises_mpa",-1),
                          ("maximum_von_mises_mpa",True)]:
            record=summary()
            record["fea"][key]=value
            with self.subTest(key=key,value=str(value)):
                with self.assertRaisesRegex(ValueError,"검증되지"):
                    save_verified_fea_snapshot(
                        self.db,UID,RUN_A,record,
                        save=self.fake_save,read=self.fake_read,lock=self.lock)
        self.assertEqual(self.writes,0)

    def test_newest_first_before_offset_pagination_and_equal_timestamps(self):
        self.save()
        self.save(RUN_B,CASE_B,17.5)
        first=recent_fea_page(self.db,limit=1,offset=0)
        second=recent_fea_page(self.db,limit=1,offset=1)
        self.assertEqual(first["items"][0]["id"],SNAP_B)
        self.assertEqual(second["items"][0]["id"],SNAP_A)
        self.assertEqual(first["total"],2)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertEqual(first["items"][0]["stage"],"fea_result")
        self.assertNotIn("maximum_von_mises_mpa",first["items"][0])
        self.assert_protected()

    def test_missing_db_listing_does_not_create_sqlite(self):
        self.db.unlink()
        self.assertEqual(recent_fea_page(self.db)["items"],[])
        self.assertFalse(self.db.exists())


class ProductionArchiveDispatch(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix="geofield-a03-dispatch-")
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        (self.root/(UID+".json")).write_text(
            json.dumps({"sha256":SHA,"mesh":{"face_ids":[1]}}),encoding="utf-8")
        (self.root/(UID+".fea_case.json")).write_text(
            json.dumps({"cad_sha256":SHA,"case_sha256":CASE_A}),
            encoding="utf-8")
        self.tasks={
            RUN_A:{"id":RUN_A,"cad_job_id":UID,"cad_sha256":SHA,
                   "case_sha256":CASE_A,"status":"complete",
                   "result":{"case_sha256":CASE_A}},
            RUN_B:{"id":RUN_B,"cad_job_id":UID,"cad_sha256":SHA,
                   "case_sha256":CASE_A,"status":"failed"},
        }
        self.calls=[]
        def verify(candidate, case, sha, _jobs_dir):
            self.calls.append(("verify",candidate["id"]))
            return dict(candidate,source_validation="INP_STA_FRD_reverified")
        def builder(_job,_dims,_ml,task,case,*_args):
            self.calls.append(("summary",task["id"]))
            return summary(task["id"],case["case_sha256"])
        def store(_db,uid,rid,data,**_args):
            self.calls.append(("save",rid))
            return SNAP_A
        self.scope={
            "STATE_LOCK":threading.RLock(),"JOBS":{UID:{"status":"complete",
                "sha256":SHA,"analysis":{}}},"FEA_JOBS":self.tasks,
            "ML_JOBS":{},"JOBS_DIR":self.root,"HISTORY_DB":self.root/"test.db",
            "json":json,"measure_geometry":lambda *_args:{},
            "reverify_task_for_display":verify,
            "build_summary":builder,
            "fea_solver_status":lambda:{},
            "r171_event":lambda *_args:None,
            "archive_save":lambda *_args:None,
            "archive_read":lambda *_args:{},
            "save_verified_fea_snapshot":store,
            "valid_uid":lambda value:isinstance(value,str) and len(value)==32,
            "sys":__import__("sys"),
        }
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),"exec"),self.scope)
    def test_exact_triggering_run_used_even_when_last_job_failed(self):
        sid=self.scope["archive_current_job"](UID,"fea_result",run_id=RUN_A)
        self.assertEqual(sid,SNAP_A)
        self.assertEqual(self.calls,[("verify",RUN_A),("summary",RUN_A),("save",RUN_A)])
    def test_last_failed_run_never_archived_as_old_complete(self):
        self.assertIsNone(self.scope["archive_current_job"](UID,"fea_result",run_id=RUN_B))
        self.assertEqual(self.calls,[])
    def test_missing_run_id_fails_closed(self):
        self.assertIsNone(self.scope["archive_current_job"](UID,"fea_result"))
        self.assertEqual(self.calls,[])


if __name__=="__main__":
    unittest.main()
