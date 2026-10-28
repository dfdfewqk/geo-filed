"""A04: explicit, permanent, narrow deletion of one FEA history result.

No legacy trash; no deletion of STEP, ML weights, shared source/job files.
SQLite remains the authority. A temporary full copy permits rollback if an
archive directory removal or SQLite COMMIT fails. No deletion without opt-in.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from pathlib import Path

HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = ("case.json", "result.json", "geofield_case.inp",
            "geofield_case.sta", "geofield_case.frd")


def _id(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _archive_matches(row, snapshot_id, expected_run, expected_sha):
    sid, stage, uid, sha, raw = row
    if (sid != snapshot_id or stage != "fea_result" or not _id(uid, HEX32)
            or not _id(sha, HEX64) or sha != expected_sha):
        raise ValueError("선택된 FEA 기록의 ID·원본 STEP 해시가 일치하지 않습니다.")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("저장된 FEA 계산 이력의 내용이 손상됐습니다.") from exc
    fea, cad = data.get("fea") or {}, data.get("cad") or {}
    case_sha = fea.get("result_case_sha256")
    if (fea.get("state") != "complete" or
            fea.get("result_run_id") != expected_run or
            cad.get("sha256") != sha or not _id(case_sha, HEX64)):
        raise ValueError("실제 계산 ID·FEA 조건·CAD 정보가 일치하지 않습니다.")
    return uid, case_sha


def _sole_owner(db, snapshot_id, run_id):
    """Never remove solver evidence if another snapshot also needs this run."""
    for other_sid, raw in db.execute(
            "SELECT id,summary_json FROM snapshots WHERE id<>?", (snapshot_id,)):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError("다른 기록의 참조 상태가 손상돼 안전하게 삭제할 수 없습니다.")
        if isinstance(data, dict) and (data.get("fea") or {}).get("result_run_id") == run_id:
            raise ValueError("다른 분석 기록이 동일한 FEA 계산 파일을 사용하고 있습니다.")


def _verified_private_folder(jobs_dir, run_id, cad_sha, case_sha):
    root = Path(jobs_dir) / "fea_runs"
    folder = root / run_id
    if (root.is_symlink() or not root.is_dir() or
            folder.is_symlink() or not folder.is_dir()):
        raise ValueError("FEA 계산 파일 폴더가 없거나 안전한 경로가 아닙니다.")
    for child in folder.rglob("*"):
        if child.is_symlink() or (not child.is_file() and not child.is_dir()):
            raise ValueError("계산 폴더에 외부 참조 또는 특수 파일이 포함됐습니다.")
    for filename in REQUIRED:
        item = folder / filename
        if item.is_symlink() or not item.is_file() or item.stat().st_size == 0:
            raise ValueError("기존 계산 파일이 누락되거나 안전하지 않습니다: " + filename)
    try:
        case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    except (UnicodeError, ValueError, OSError) as exc:
        raise ValueError("계산 조건/결과 파일을 읽을 수 없습니다.") from exc
    if (case.get("cad_sha256") != cad_sha or
            case.get("case_sha256") != case_sha or
            result.get("cad_sha256") != cad_sha or
            result.get("case_sha256") != case_sha or
            result.get("status") != "solver_executed_result_parsed"):
        raise ValueError("FEA 계산 파일의 CAD·조건 서명이 저장 이력과 다릅니다.")
    return folder


def _restore_after_failure(original, stage, backup):
    """Restore untouched backup, even if stage removal stopped mid-directory."""
    if not original.exists():
        if backup.is_dir():
            os.replace(backup, original)
        elif stage.is_dir():
            os.replace(stage, original)
    if not original.is_dir():
        raise RuntimeError("삭제 실패 후 원래 계산 폴더를 복원하지 못했습니다.")
    # A partially deleted staging folder is not a historic source directory;
    # keep it on disk if cleanup is also faulty. Never touch unrelated files.
    if stage.is_dir():
        try:
            shutil.rmtree(stage)
        except OSError:
            pass
    if backup.is_dir():
        try:
            shutil.rmtree(backup)
        except OSError:
            pass


def delete_one_fea_record(db_path, jobs_dir, snapshot_id, run_id, cad_sha, *,
                          confirmation, lock, active_run_ids=(),
                          active_snapshot_ids=(), remove_tree=None):
    """Delete exactly one explicitly selected run and snapshot, or roll back.

    SQLite BEGIN IMMEDIATE is held until the run directory is removed. The
    complete backup persists until COMMIT, permitting restoration after file
    delete errors and transaction failures. Concurrent app callers use lock.
    Other snapshots and protected paths are never modified.
    """
    if confirmation != "PERMANENT_DELETE_FEA_RESULT":
        raise ValueError("영구 삭제에 대한 별도의 명시적 확인이 필요합니다.")
    if (not _id(snapshot_id, HEX32) or not _id(run_id, HEX32) or
            not _id(cad_sha, HEX64)):
        raise ValueError("FEA 삭제 대상 ID 또는 원본 해시 형식이 잘못됐습니다.")
    if run_id in active_run_ids or snapshot_id in active_snapshot_ids:
        raise ValueError("실행 중이거나 아직 처리 중인 FEA 기록은 삭제할 수 없습니다.")
    db_path = Path(db_path)
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("기존 FEA 이력 SQLite 파일이 없습니다.")
    remove_tree = remove_tree or shutil.rmtree
    with lock:
        with sqlite3.connect(db_path, timeout=10, isolation_level=None) as db:
            db.execute("BEGIN IMMEDIATE")
            stage = backup = original = None
            committed = False
            try:
                row = db.execute(
                    "SELECT id,stage,job_id,cad_sha256,summary_json "
                    "FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
                if row is None:
                    raise ValueError("선택한 FEA 기록이 없습니다.")
                _uid, case_sha = _archive_matches(row, snapshot_id, run_id, cad_sha)
                _sole_owner(db, snapshot_id, run_id)
                original = _verified_private_folder(jobs_dir, run_id, cad_sha, case_sha)
                stage = original.parent / (".geofield-a04-" + snapshot_id + ".staging")
                backup = original.parent / (".geofield-a04-" + snapshot_id + ".backup")
                if stage.exists() or backup.exists() or stage.is_symlink() or backup.is_symlink():
                    raise ValueError("이전 삭제 작업이 남아 있습니다. 원본을 확인하기 전 재시도하지 않습니다.")
                # Any copy failure leaves both original and SQLite untouched.
                shutil.copytree(original, backup, symlinks=False)
                os.replace(original, stage)
                # Partial filesystem failures are recoverable from full backup.
                remove_tree(stage)
                deleted = db.execute(
                    "DELETE FROM snapshots WHERE id=? AND stage='fea_result' "
                    "AND cad_sha256=?", (snapshot_id, cad_sha))
                if deleted.rowcount != 1:
                    raise RuntimeError("FEA 이력 삭제 중 기록 상태가 변경됐습니다.")
                db.execute("COMMIT")
                committed = True
            except Exception as exc:
                if not committed:
                    try:
                        db.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                    try:
                        if original is not None and backup is not None and stage is not None:
                            _restore_after_failure(original, stage, backup)
                    except Exception as recovery_error:
                        raise RuntimeError(
                            "삭제 실패 후 자동 복원도 실패했습니다. 백업을 지우지 마세요: " +
                            str(recovery_error)) from exc
                raise
        # All user-visible records and target run files are permanently
        # deleted. Temporary backup cleanup can fail independently and is
        # reported honestly; no additional user file is deleted.
        try:
            shutil.rmtree(backup)
            cleanup = "complete"
        except OSError:
            cleanup = "backup_cleanup_required"
        return {"ok": True, "deleted_snapshot_id": snapshot_id,
                "deleted_run_id": run_id, "cad_sha256": cad_sha,
                "permanent": True, "other_records_preserved": True,
                "temporary_cleanup": cleanup}
