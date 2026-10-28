"""A04 destructive path regression: temporary SQLite and synthetic solver evidence only."""
import copy
import json
import sqlite3
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from fea_history_delete_a04 import delete_one_fea_record

UID="1"*32
SID="2"*32
RID="3"*32
OTHER_SID="4"*32
OTHER_RID="5"*32
CAD="a"*64
CASE="b"*64
CONFIRM="PERMANENT_DELETE_FEA_RESULT"
EVIDENCE=("geofield_case.inp","geofield_case.sta","geofield_case.frd")


@pytest.fixture
def source(tmp_path):
    db=tmp_path/"history.sqlite3"
    jobs=tmp_path/"jobs"
    runs=jobs/"fea_runs"
    runs.mkdir(parents=True)
    protected_step=tmp_path/"original.step"
    protected_model=tmp_path/"r12-model.joblib"
    protected_step.write_bytes(b"ORIGINAL STEP IS PROTECTED")
    protected_model.write_bytes(b"MODEL WEIGHTS ARE PROTECTED")
    def insert(sid, rid, stage="fea_result",case=CASE):
        summary={"cad":{"sha256":CAD},
                 "fea":{"state":"complete","result_run_id":rid,
                        "result_case_sha256":case,
                        "maximum_von_mises_mpa":12.0,
                        "maximum_displacement_mm":0.012}}
        with sqlite3.connect(db) as con:
            con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?)",
                        (sid,stage,UID,CAD,"2026-10-28",json.dumps(summary)))
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE snapshots (id TEXT PRIMARY KEY,stage TEXT,job_id TEXT,"
                    "cad_sha256 TEXT,created_at TEXT,summary_json TEXT)")
    for rid in (RID,OTHER_RID):
        folder=runs/rid
        folder.mkdir()
        (folder/"case.json").write_text(
            json.dumps({"cad_sha256":CAD,"case_sha256":CASE}),encoding="utf-8")
        (folder/"result.json").write_text(
            json.dumps({"cad_sha256":CAD,"case_sha256":CASE,
                        "status":"solver_executed_result_parsed"}),encoding="utf-8")
        for name in EVIDENCE:
            (folder/name).write_bytes((rid+name).encode())
        (folder/"worker.log").write_text("unrelated test log")
    insert(SID,RID)
    insert(OTHER_SID,OTHER_RID)
    return {"db":db,"jobs":jobs,"runs":runs,"insert":insert,
            "protected":(protected_step,protected_model),
            "lock":threading.RLock()}


def delete(source,*,sid=SID,rid=RID,cad=CAD,confirmation=CONFIRM,**kw):
    return delete_one_fea_record(source["db"],source["jobs"],sid,rid,cad,
                                 confirmation=confirmation,lock=source["lock"],**kw)


def assert_untouched(source):
    assert source["protected"][0].read_bytes()==b"ORIGINAL STEP IS PROTECTED"
    assert source["protected"][1].read_bytes()==b"MODEL WEIGHTS ARE PROTECTED"
    assert (source["runs"]/OTHER_RID/"geofield_case.frd").read_bytes()==(
        OTHER_RID+"geofield_case.frd").encode()


def has_row(source,sid=SID):
    with sqlite3.connect(source["db"]) as cx:
        return cx.execute("SELECT count(*) FROM snapshots WHERE id=?",(sid,)).fetchone()[0]==1


def test_explicit_one_run_permanently_deleted_preserving_other_files(source):
    result=delete(source)
    assert result["ok"] is True
    assert result["temporary_cleanup"]=="complete"
    assert result["permanent"] is True
    assert not has_row(source)
    assert not (source["runs"]/RID).exists()
    assert has_row(source,OTHER_SID)
    assert not list(source["runs"].glob(".geofield-a04-*"))
    assert_untouched(source)


@pytest.mark.parametrize("kw",[
    {"confirmation":""},
    {"sid":"../"+SID},
    {"rid":OTHER_RID},
    {"cad":"c"*64},
    {"active_run_ids":[RID]},
    {"active_snapshot_ids":[SID]},
    {"active_job_ids":[UID]},
])
def test_no_delete_when_request_unconfirmed_or_identity_active(source,kw):
    with pytest.raises(ValueError):
        delete(source,**kw)
    assert has_row(source)
    assert (source["runs"]/RID/"geofield_case.frd").is_file()
    assert_untouched(source)


def test_same_run_used_by_another_snapshot_never_deletes_shared_evidence(source):
    source["insert"]("6"*32,RID,stage="fea_case")
    with pytest.raises(ValueError,match="다른 분석 기록"):
        delete(source)
    assert has_row(source)
    assert (source["runs"]/RID).is_dir()
    assert_untouched(source)


def test_missing_required_file_blocks_deletion_without_touching_database(source):
    (source["runs"]/RID/"geofield_case.sta").unlink()
    with pytest.raises(ValueError,match="누락"):
        delete(source)
    assert has_row(source)
    assert (source["runs"]/RID/"geofield_case.frd").is_file()
    assert_untouched(source)


def test_wrong_disk_case_sha_blocks_deletion(source):
    f=source["runs"]/RID/"case.json"
    data=json.loads(f.read_text());data["case_sha256"]="d"*64
    f.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="서명"):
        delete(source)
    assert has_row(source)
    assert_untouched(source)


def test_recursive_symlink_never_followed(source):
    outside=source["protected"][0]
    (source["runs"]/RID/"shortcut.step").symlink_to(outside)
    with pytest.raises(ValueError,match="외부 참조"):
        delete(source)
    assert has_row(source)
    assert outside.is_file()
    assert_untouched(source)


def test_partial_directory_removal_restores_all_files_and_sqlite(source):
    folder=source["runs"]/RID
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    def break_cleanup(stage):
        (stage/"geofield_case.frd").unlink()
        raise OSError("simulated Windows locked directory")
    with pytest.raises(OSError,match="locked directory"):
        delete(source,remove_tree=break_cleanup)
    assert has_row(source)
    assert {p.name:p.read_bytes() for p in folder.iterdir()}==before
    assert not list(source["runs"].glob(".geofield-a04-*"))
    assert_untouched(source)


def test_database_commit_error_restores_full_directory_and_row(source):
    import fea_history_delete_a04 as module
    original_connect=sqlite3.connect
    class FailedCommit:
        def __init__(self,base):self.base=base
        def __enter__(self):return self
        def __exit__(self,*args):return self.base.__exit__(*args)
        def close(self):return self.base.close()
        def execute(self,sql,*args):
            if sql=="COMMIT":raise sqlite3.OperationalError("simulated db commit failure")
            return self.base.execute(sql,*args)
    def wrapped(*args,**kw):
        return FailedCommit(original_connect(*args,**kw))
    protected_frd=(source["runs"]/RID/"geofield_case.frd").read_bytes()
    with patch.object(module.sqlite3,"connect",side_effect=wrapped):
        with pytest.raises(sqlite3.OperationalError,match="simulated db commit"):
            delete(source)
    assert has_row(source)
    assert (source["runs"]/RID/"geofield_case.frd").read_bytes()==protected_frd
    assert_untouched(source)


def test_invalid_snapshot_json_rejected_without_deleting_files(source):
    with sqlite3.connect(source["db"]) as cx:
        cx.execute("UPDATE snapshots SET summary_json=? WHERE id=?",("{bad",SID))
    with pytest.raises(ValueError,match="손상"):
        delete(source)
    assert has_row(source)
    assert (source["runs"]/RID).is_dir()
    assert_untouched(source)


def test_production_server_requires_explicit_origin_and_confirmation():
    root=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
    src=root.read_text(encoding="utf-8")
    assert "if path.startswith('/api/history/fea-delete/')" in src
    assert "X-GeoField-FEA-Delete" in src
    assert "PERMANENT_DELETE_FEA_RESULT" not in src  # passed into deletion module only
    assert "delete_one_fea_record(" in src
    assert "CURRENT.pop('verified_restored_run_id',None)" in src
    front=(root.parent/"frontend"/"cad.js").read_text(encoding="utf-8")
    assert "/api/history/fea-delete" not in front
