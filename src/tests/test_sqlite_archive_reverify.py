"""Real SQLite archived-result lookup with an isolated synthetic solver archive.

Exercises the production r184_verified_archive_numbers() function via AST.
No original STEP/INP/STA/FRD is read; synthetic restore_payload is intentionally
not proof of actual FEA. Reopen the DB for every read, like after app restart.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf8"))
nodes=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="r184_verified_archive_numbers"]
assert len(nodes)==1
UID="1"*32
RUN="2"*32
SID="3"*32
SHA="a"*64
CASE="b"*64
VERIFIED={
    "cad_sha256":SHA, "case_sha256":CASE,
    "results":{"maximum_nodal_von_mises_mpa":14.512,
               "maximum_displacement_mm":0.05698},
    "mesh":{"tetrahedron_count":8611,"node_count":2798},
}
CASE_DATA={"case_sha256":CASE,"cad_sha256":SHA,
           "material":{"name":"Aluminum 6061-T6"},
           "boundary_conditions":{"total_force_n":49.03325,
                                  "force_direction_unit":[0,0,-1],
                                  "fixed_face_ids":[1],"load_face_ids":[3]},
           "preset_metadata":{"mass_kg":5}}
def valid_uid(val):
    return isinstance(val,str) and len(val)==32 and all(c in "0123456789abcdef" for c in val)
def evidence_record():
    return {"cad":{"sha256":SHA,"name":"saved-bracket.step"},
            "fea":{"state":"complete","result_run_id":RUN,
                   "result_case_sha256":CASE,
                   "maximum_von_mises_mpa":14.512,
                   "maximum_displacement_mm":0.05698,
                   "setup":{"fixed_faces":[1],"load_faces":[3]}}}

class SQLiteReverifyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="geofield-history-sqlite-")
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.db=self.directory/"geofield_review_history.sqlite3"
        self.protected=self.directory/"prior_user_frd.frd"
        self.protected.write_bytes(b"synthetic protected evidence - must not change")
        with sqlite3.connect(self.db) as cn:
            cn.execute("""CREATE TABLE snapshots (
                id TEXT PRIMARY KEY, stage TEXT NOT NULL,
                job_id TEXT NOT NULL, cad_sha256 TEXT NOT NULL,
                summary_json TEXT NOT NULL)""")
            cn.execute("INSERT INTO snapshots VALUES (?,?,?,?,?)",
                       (SID,"fea_result",UID,SHA,json.dumps(evidence_record())))
        self.fixture={
            "cad":{"sha":SHA,"case":copy.deepcopy(CASE_DATA)},
            "rid":RUN, "verified":copy.deepcopy(VERIFIED), "field":{"synthetic":True}}
        def fake_restore(jobs,uid,run_hint=None):
            self.assertEqual(uid,UID)
            self.assertEqual(run_hint,RUN)
            f=self.fixture
            return (copy.deepcopy(f["cad"]),f["rid"],
                    copy.deepcopy(f["verified"]),copy.deepcopy(f["field"]))
        self.ns={"HISTORY_DB":self.db,"JOBS_DIR":self.directory,
                 "sqlite3":sqlite3,"json":json,"valid_uid":valid_uid,
                 "restore_payload":fake_restore}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),"exec"),self.ns)
        self.read=self.ns["r184_verified_archive_numbers"]
    def untouched(self):
        self.assertEqual(self.protected.read_bytes(),
                         b"synthetic protected evidence - must not change")
    def replace_saved(self,fn):
        with sqlite3.connect(self.db) as cn:
            rec=json.loads(cn.execute("SELECT summary_json FROM snapshots WHERE id=?",
                                       (SID,)).fetchone()[0])
            fn(rec)
            cn.execute("UPDATE snapshots SET summary_json=? WHERE id=?",
                       (json.dumps(rec),SID))
    def test_sqlite_reopen_after_restart_matches_verified_run(self):
        db_before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        report=self.read(SID)
        self.assertTrue(report["ok"])
        self.assertTrue(report["read_only"])
        self.assertTrue(report["current_session_unchanged"])
        self.assertEqual(report["run_id"],RUN)
        self.assertEqual(report["cad_sha256"],SHA)
        self.assertEqual(report["case_sha256"],CASE)
        self.assertEqual(report["maximum_von_mises_mpa"],14.512)
        self.assertEqual(report["mesh"]["tetrahedra"],8611)
        self.assertEqual(report["mesh"]["nodes"],2798)
        self.assertEqual(report["conditions"]["fixed_faces"],[1])
        self.assertEqual(report["conditions"]["load_faces"],[3])
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),db_before)
        self.untouched()
    def test_another_snapshot_does_not_inherit_old_result(self):
        with self.assertRaisesRegex(ValueError,"완료된 FEA"):
            self.read("4"*32)
        self.untouched()
    def test_non_fea_record_cannot_claim_actual_calculix(self):
        with sqlite3.connect(self.db) as cn:
            cn.execute("UPDATE snapshots SET stage='ml' WHERE id=?",(SID,))
        with self.assertRaisesRegex(ValueError,"완료된 FEA"):
            self.read(SID)
        self.untouched()
    def test_saved_run_id_mismatch_rejected(self):
        self.fixture["rid"]="5"*32
        with self.assertRaisesRegex(ValueError,"식별자가 다릅니다"):
            self.read(SID)
        self.untouched()
    def test_saved_case_sha_mismatch_rejected(self):
        self.fixture["cad"]["case"]["case_sha256"]="c"*64
        with self.assertRaisesRegex(ValueError,"식별자가 다릅니다"):
            self.read(SID)
        self.untouched()
    def test_cad_sha_mismatch_rejected(self):
        self.fixture["verified"]["cad_sha256"]="d"*64
        with self.assertRaisesRegex(ValueError,"식별자가 다릅니다"):
            self.read(SID)
        self.untouched()
    def test_corrupt_stored_stress_number_rejected(self):
        self.replace_saved(lambda r:r["fea"].update(maximum_von_mises_mpa=999))
        with self.assertRaisesRegex(ValueError,"FRD 계산 수치"):
            self.read(SID)
        self.untouched()
    def test_corrupt_stored_displacement_rejected(self):
        self.replace_saved(lambda r:r["fea"].update(maximum_displacement_mm=0.9))
        with self.assertRaisesRegex(ValueError,"FRD 계산 수치"):
            self.read(SID)
        self.untouched()
    def test_bad_snapshot_id_does_not_query_or_change_data(self):
        with self.assertRaisesRegex(ValueError,"ID 형식"):
            self.read("../../fake")
        self.untouched()
    def test_missing_database_fails_without_creating_one(self):
        self.db.unlink()
        with self.assertRaisesRegex(ValueError,"DB 파일"):
            self.read(SID)
        self.assertFalse(self.db.exists())
        self.untouched()

if __name__=="__main__":
    unittest.main()
