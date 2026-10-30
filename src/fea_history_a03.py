"""Read-only identity checks and idempotent archive handoff for completed FEA.

The installed history_store remains the sole SQLite writer. This module never
recreates missing Windows-only modules or touches STEP/INP/STA/FRD artifacts.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path

HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _valid_id(text, pattern):
    return isinstance(text, str) and bool(pattern.fullmatch(text))


def _identifiers(job_id, run_id, summary):
    if not _valid_id(job_id, HEX32) or not _valid_id(run_id, HEX32):
        raise ValueError("FEA 기록 저장에 필요한 CAD/계산 실행 ID가 잘못됐습니다.")
    if not isinstance(summary, dict):
        raise ValueError("FEA 보존 분석 요약 형식이 잘못됐습니다.")
    cad, fea = summary.get("cad") or {}, summary.get("fea") or {}
    sha, case_sha = cad.get("sha256"), fea.get("result_case_sha256")
    if (not _valid_id(sha, HEX64) or not _valid_id(case_sha, HEX64)
            or fea.get("state") != "complete" or fea.get("result_run_id") != run_id):
        raise ValueError("실제 FEA 결과와 CAD/조건 해시가 일치하지 않습니다.")
    for key in ("maximum_von_mises_mpa", "maximum_displacement_mm"):
        value = fea.get(key)
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise ValueError("실제 FEA 응력·변위 값이 검증되지 않았습니다.")
    return sha, case_sha


def _check_saved(entry, job_id, run_id, summary):
    sha, case_sha = _identifiers(job_id, run_id, summary)
    if not isinstance(entry, dict):
        raise ValueError("SQLite에서 저장된 FEA 기록을 다시 읽을 수 없습니다.")
    cad, fea = entry.get("cad") or {}, entry.get("fea") or {}
    if (cad.get("sha256") != sha or fea.get("state") != "complete"
            or fea.get("result_run_id") != run_id
            or fea.get("result_case_sha256") != case_sha):
        raise ValueError("저장된 계산 ID·CAD·FEA 조건 서명이 일치하지 않습니다.")
    for key in ("maximum_von_mises_mpa", "maximum_displacement_mm"):
        actual, persisted = summary["fea"][key], fea.get(key)
        if (type(persisted) not in (float, int) or not math.isfinite(persisted)
                or persisted < 0 or not math.isclose(
                    persisted, actual, rel_tol=1e-9, abs_tol=1e-10)):
            raise ValueError("저장된 실제 FEA 응력·변위가 원래 결과와 다릅니다.")


def save_verified_fea_snapshot(db_path, job_id, run_id, summary, *, save, read, lock):
    """One snapshot per run, not per CAD; do not silently retry a failed write.

    Must run only after independent INP/STA/FRD reverification. The lock
    serializes duplicate callbacks in this process; the installed history
    module continues to own the actual SQLite insert/transaction.
    """
    sha, _case_sha = _identifiers(job_id, run_id, summary)
    db_path = Path(db_path)
    with lock:
        existing = []
        if db_path.is_file():
            with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
                rows = db.execute(
                    "SELECT id,cad_sha256,summary_json FROM snapshots "
                    "WHERE stage='fea_result' AND job_id=?", (job_id,))
                for sid, stored_sha, raw in rows:
                    entry = json.loads(raw)
                    if (entry.get("fea") or {}).get("result_run_id") == run_id:
                        if stored_sha != sha:
                            raise ValueError("기존 FEA 계산 기록의 CAD 해시가 다릅니다.")
                        _check_saved(entry, job_id, run_id, summary)
                        existing.append(sid)
        if len(existing) > 1:
            raise ValueError("동일 FEA 실행에 중복된 저장 기록이 있습니다.")
        if existing:
            return existing[0]
        sid = save(db_path, "fea_result", job_id, summary)
        if not _valid_id(sid, HEX32):
            raise ValueError("SQLite 저장 기록 ID가 반환되지 않았습니다.")
        _check_saved(read(db_path, sid), job_id, run_id, summary)
        return sid


def recent_fea_page(db_path, *, limit=50, offset=0):
    """Order BEFORE pagination; historic rows are only metadata until restored."""
    if type(limit) is not int or not 1 <= limit <= 2000 or type(offset) is not int or offset < 0:
        raise ValueError("FEA 기록 조회 페이지 범위 오류")
    db_path = Path(db_path)
    if not db_path.is_file():
        return {"items": [], "offset": offset, "limit": limit, "total": 0, "has_more": False}
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        total = db.execute(
            "SELECT count(*) FROM snapshots WHERE stage='fea_result'").fetchone()[0]
        rows = db.execute(
            "SELECT id,stage,job_id,cad_sha256,cad_name,created_at "
            "FROM snapshots WHERE stage='fea_result' "
            "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
    items = [
        {"id": sid, "stage": stage, "job_id": uid, "cad_sha256": sha,
         "cad_name": name, "created_at": created}
        for sid, stage, uid, sha, name, created in rows
    ]
    return {"items": items, "offset": offset, "limit": limit,
            "total": total, "has_more": offset + len(items) < total}
