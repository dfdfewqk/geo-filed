"""A05: exercise the production FEA callback with synthetic Gmsh/CCX files only.

No real solver or user archive is accessed. Every test executes the actual
execute_fea function extracted from its production module.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf8"))
FUNCS = [node for node in TREE.body if isinstance(node,ast.FunctionDef)
         and node.name=="execute_fea"]
assert len(FUNCS)==1

CAD="a"*64
CASE="b"*64
UID="1"*32
RUN="2"*32
OTHER="3"*32
RESULT={"schema":"geofield-fea-result-v1",
        "status":"solver_executed_result_parsed",
        "cad_sha256":CAD,"case_sha256":CASE,
        "mesh":{"node_count":100,"tetrahedron_count":70},
        "results":{"maximum_nodal_von_mises_mpa":15.1,
                   "maximum_displacement_mm":0.023,"parsed_nodes":100}}


def build_scope(root,*,worker=False,verify_fail=False,wrong_result=False,
                switch_during_verify=False,solver_fail=False,worker_fail=False):
    jobs=root/"jobs"
    jobs.mkdir()
    uploaded=jobs/(RUN+".fea_input.step")
    uploaded.write_bytes(b"ONLY TEMPORARY COPIED STEP")
    case={"cad_sha256":CAD,"case_sha256":CASE,"schema":"geofield-fea-case-v1"}
    (jobs/(UID+".fea_case.json")).write_text(json.dumps(case),encoding="utf-8")
    result=json.loads(json.dumps(RESULT))
    if wrong_result:
        result["case_sha256"]="c"*64
    if worker:
        # B01: test a present Python worker, never fabricate production solver.
        (root/"fea_engine_worker.py").write_text(
            "def main(): return 0\n",encoding="utf-8")
    state={"status":"queued","cad_job_id":UID,"cad_sha256":CAD,"case_sha256":CASE}
    tasks={RUN:state}
    current={"job_id":UID}
    notes=[]
    archives=[]
    validations=[]
    def fake_solver(_step,_case,_model,folder,_ccx,*,progress_callback=None):
        folder.mkdir(parents=True,exist_ok=False)
        for name in ("geofield_case.inp","geofield_case.sta","geofield_case.frd"):
            (folder/name).write_bytes(("synthetic only "+name).encode())
        if progress_callback:
            progress_callback("mesh","메시 생성 중")
            progress_callback("solver","CalculiX 계산 중")
            progress_callback("verification","결과 검증 중")
        if solver_fail:
            raise RuntimeError("synthetic CCX solver failed")
        return result
    def fake_verify(task,_case,_sha,directory):
        folder=directory/"fea_runs"/RUN
        assert tasks[RUN]["status"]=="running"
        assert all((folder/name).is_file() for name in (
            "case.json","result.json","geofield_case.inp",
            "geofield_case.sta","geofield_case.frd"))
        validations.append(task["id"])
        if switch_during_verify:
            current["job_id"]=OTHER
        if verify_fail:
            return dict(task,status="failed",message="synthetic damaged FRD")
        return dict(task,source_validation="INP_STA_FRD_reverified")
    def archive(_uid,kind,run_id=None):
        archives.append((kind,run_id))
        if kind=="fea_result":
            assert tasks[RUN]["status"]=="complete"
            assert tasks[RUN]["source_validation"]=="INP_STA_FRD_reverified"
            return "4"*32
        return None
    def fake_worker_run(command,**kwargs):
        folder=jobs/"fea_runs"/RUN
        folder.mkdir(parents=True,exist_ok=True)
        for name in ("geofield_case.inp","geofield_case.sta","geofield_case.frd"):
            (folder/name).write_bytes(("synthetic worker "+name).encode())
        (folder/"worker_result.json").write_text(json.dumps(result),encoding="utf-8")
        if worker_fail:
            return SimpleNamespace(returncode=1,stdout="",stderr="worker CCX failure")
        return SimpleNamespace(returncode=0,stdout="worker success",stderr="")
    class Subprocess:
        CREATE_NO_WINDOW=0
        @staticmethod
        def run(*args,**kwargs):
            return fake_worker_run(*args,**kwargs)
    def save_atomic(path,data):
        Path(path).write_text(json.dumps(data),encoding="utf-8")
    scope={
        "os":os,"sys":sys,"json":json,"STATE_LOCK":threading.RLock(),
        "FEA_JOBS":tasks,"JOBS":{UID:{"status":"complete","sha256":CAD}},
        "CURRENT":current,"JOBS_DIR":jobs,"ROOT":root,
        "r171_note":lambda *args:notes.append(args),
        "gmsh_python_status":lambda:{"ok":True,"path":"/different/gmsh-python"} if worker else {"ok":False},
        "run_real_fea":fake_solver,
        "reverify_task_for_display":fake_verify,
        "archive_current_job":archive,
        "atomic_json":save_atomic,
        "prepare_python_environment":lambda *_args:{},
        "subprocess":Subprocess,
    }
    exec(compile(ast.Module(body=FUNCS,type_ignores=[]),str(SOURCE),"exec"),scope)
    return scope,uploaded,case,tasks,archives,validations,notes


def run_case(**kw):
    temp=tempfile.TemporaryDirectory(prefix="geofield-a05-")
    root=Path(temp.name)
    env=build_scope(root,**kw)
    scope,uploaded,case,tasks,archives,validations,notes=env
    scope["execute_fea"](RUN,UID,uploaded,case,{"sha256":CAD},"ccx")
    assert not uploaded.exists()
    return temp,root,env


def test_real_completed_solver_only_published_after_independent_evidence_check():
    temp,root,env=run_case()
    try:
        _,_,_,tasks,archives,validations,_=env
        assert tasks[RUN]["status"]=="complete"
        assert tasks[RUN]["stage"]=="complete"
        assert tasks[RUN]["source_validation"]=="INP_STA_FRD_reverified"
        assert tasks[RUN]["history_snapshot_id"]=="4"*32
        assert tasks[RUN]["history_archive_status"]=="saved"
        assert validations==[RUN]
        assert archives==[("fea_result",RUN)]
        assert not (root/"jobs"/"fea_runs"/RUN/"error.log").exists()
    finally:
        temp.cleanup()


@pytest.mark.parametrize("reason",["verify_fail","wrong_result","switch_during_verify","solver_fail"])
def test_failed_or_stale_solver_never_publishes_success_or_old_result(reason):
    temp,root,env=run_case(**{reason:True})
    try:
        _,_,_,tasks,archives,_,_=env
        assert tasks[RUN]["status"]=="failed"
        assert tasks[RUN]["stage"]=="failed"
        assert "result" not in tasks[RUN]
        assert "source_validation" not in tasks[RUN]
        assert all(stage!="fea_result" for stage,_ in archives)
        assert (root/"jobs"/"fea_runs"/RUN/"error.log").is_file()
    finally:
        temp.cleanup()


def test_separate_python_worker_not_assumed_to_have_fine_grained_stage():
    temp,root,env=run_case(worker=True)
    try:
        _,_,_,tasks,archives,validations,_=env
        assert tasks[RUN]["status"]=="complete"
        assert validations==[RUN]
        assert archives==[("fea_result",RUN)]
        assert tasks[RUN]["history_archive_status"]=="saved"
        assert (root/"jobs"/"fea_runs"/RUN/"worker.log").is_file()
    finally:
        temp.cleanup()


def test_failed_python_worker_does_not_archive_or_verify():
    temp,root,env=run_case(worker=True,worker_fail=True)
    try:
        _,_,_,tasks,archives,validations,_=env
        assert tasks[RUN]["status"]=="failed"
        assert validations==[]
        assert all(stage!="fea_result" for stage,_ in archives)
        assert "result" not in tasks[RUN]
    finally:
        temp.cleanup()


def test_missing_or_changed_solver_case_during_execution_rejected():
    temp=tempfile.TemporaryDirectory(prefix="geofield-a05-stale-")
    try:
        root=Path(temp.name)
        scope,uploaded,case,tasks,archives,_,_=build_scope(root)
        (root/"jobs"/(UID+".fea_case.json")).write_text(
            json.dumps(dict(case,case_sha256="c"*64)),encoding="utf-8")
        scope["execute_fea"](RUN,UID,uploaded,case,{"sha256":CAD},"ccx")
        assert tasks[RUN]["status"]=="failed"
        assert all(stage!="fea_result" for stage,_ in archives)
        assert "result" not in tasks[RUN]
    finally:
        temp.cleanup()


def test_progress_callback_and_failure_policies_stay_in_production():
    source=SOURCE.read_text(encoding="utf8")
    block=ast.get_source_segment(source,FUNCS[0])
    assert "progress_callback=report_progress" in block
    assert "checked=reverify_task_for_display(" in block
    assert block.index("checked=reverify_task_for_display(") < block.index("status='complete',stage='complete'")
    assert "별도 Gmsh Python 해석 중 · 세부 단계 확인 불가" in block
    assert "FEA_JOBS[run_id].pop('result',None)" in block
