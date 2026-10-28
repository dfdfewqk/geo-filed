"""GeoField FEA archive restoration must not replace the active CAD during a solve.

Exercises the production restore function with in-memory verified archive evidence
so no private SQLite, original STEP, Gmsh, CalculiX, or Windows app is required.
"""
from __future__ import annotations

import ast
import copy
import threading
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "payload" / "GeoField_CAD_Analysis.py"
CAD_SHA = "a" * 64
CASE_SHA = "b" * 64
OLD_JOB = "1" * 32
NEW_JOB = "2" * 32
RUN = "3" * 32


def _restore_fixture(mesh_status=None, fea_status=None):
    source = BACKEND.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef)
        and n.name == "r172_restore"
    )
    compiled = compile(ast.Module(body=[function], type_ignores=[]), str(BACKEND), "exec")
    cad = {
        "sha": CAD_SHA,
        "analysis": {"sha256": CAD_SHA, "source": "verified-history.step"},
        "model": {"sha256": CAD_SHA},
        "case": {"cad_sha256": CAD_SHA, "case_sha256": CASE_SHA},
    }
    result = {"cad_sha256": CAD_SHA, "case_sha256": CASE_SHA}
    original_job = {"id": OLD_JOB, "status": "complete"}
    current = {"job_id": OLD_JOB, "pending_job_id": OLD_JOB}
    jobs = {OLD_JOB: original_job}
    fea_jobs = (
        {("4" * 32): {"status": fea_status}}
        if fea_status is not None else {}
    )
    mesh_studies = (
        {("5" * 32): {"status": mesh_status}}
        if mesh_status is not None else {}
    )
    namespace = {
        "STATE_LOCK": threading.RLock(),
        "CURRENT": current,
        "JOBS": jobs,
        "FEA_JOBS": fea_jobs,
        "MESH_STUDIES": mesh_studies,
        "ACTIVE": {"queued", "running"},
        "JOBS_DIR": Path("/unused-in-memory"),
        "restore_payload": lambda directory, uid, run_hint=None: (
            copy.deepcopy(cad), RUN, copy.deepcopy(result), None
        ),
        "rule_findings": lambda model: [],
    }
    exec(compiled, namespace)
    return namespace["r172_restore"], namespace


@pytest.mark.parametrize("mesh_status", ["queued", "running"])
def test_active_mesh_series_blocks_restoration_without_mutating_session(mesh_status):
    restore, state = _restore_fixture(mesh_status=mesh_status)
    previous = copy.deepcopy({
        name: state[name] for name in ("CURRENT", "JOBS", "FEA_JOBS", "MESH_STUDIES")
    })
    with pytest.raises(ValueError, match="메시 연속 계산 중"):
        restore(NEW_JOB, run_hint=RUN)
    for name, expected in previous.items():
        assert state[name] == expected


@pytest.mark.parametrize("fea_status", ["queued", "running"])
def test_existing_single_fea_guard_remains_active(fea_status):
    restore, state = _restore_fixture(fea_status=fea_status)
    with pytest.raises(ValueError, match="FEA 계산 중"):
        restore(NEW_JOB, run_hint=RUN)
    assert state["CURRENT"]["job_id"] == OLD_JOB


@pytest.mark.parametrize("mesh_status", [None, "complete", "failed", "cancelled"])
def test_finished_mesh_series_does_not_prevent_verified_restore(mesh_status):
    restore, state = _restore_fixture(mesh_status=mesh_status)
    response = restore(NEW_JOB, run_hint=RUN)
    assert response["status"] == "complete"
    assert response["cad_sha256"] == CAD_SHA
    assert response["case_sha256"] == CASE_SHA
    assert response["run_id"] == RUN
    assert state["CURRENT"]["job_id"] == NEW_JOB
    assert state["CURRENT"]["verified_restored_run_id"] == RUN
    assert state["JOBS"][OLD_JOB]["status"] == "complete"
