"""B02: solver workspace freshness and temporary STEP ownership.

All FEA task callbacks run in isolated temp directories with a fake solver.
No FreeCAD, Gmsh, CCX, live STEP or actual Windows installed sources are used.
"""
from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import types

import pytest

from fea_b02_workspace import (
    SOLVER_OUTPUTS, existing_worker_is_safe, owned_temporary_step,
    validate_clean_solver_artifacts, validate_new_run,
)
from test_fea_execution_a05 import build_scope, CAD, RUN, UID, RESULT

SOURCE = Path(__file__).resolve().parents[1] / "payload" / "fea_solver.py"


def test_fresh_run_workspace_allows_only_empty_run_dir(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    target = jobs / "fea_runs" / RUN
    assert validate_new_run(jobs, RUN) == target
    target.mkdir(parents=True)
    assert validate_new_run(jobs, RUN) == target
    (target / "geofield_case.frd").write_bytes(b"OLD FRD: never trust")
    with pytest.raises(ValueError, match="재사용"):
        validate_new_run(jobs, RUN)
    assert (target / "geofield_case.frd").read_bytes() == b"OLD FRD: never trust"


@pytest.mark.parametrize("name", sorted(SOLVER_OUTPUTS))
def test_old_solver_artifact_is_never_reused(name, tmp_path):
    folder = tmp_path / RUN
    folder.mkdir()
    (folder / name).write_bytes(b"STALE OR FALSE PASS")
    with pytest.raises(ValueError, match="재사용"):
        validate_clean_solver_artifacts(folder)
    assert (folder / name).read_bytes() == b"STALE OR FALSE PASS"


def test_queued_worker_input_is_allowed_only_without_solver_artifacts(tmp_path):
    folder = tmp_path / "runner"
    folder.mkdir()
    (folder / "worker_case.json").write_text('{"test":"only"}')
    (folder / "worker_model.json").write_text('{"test":"only"}')
    assert validate_clean_solver_artifacts(folder) is True
    (folder / "result.json").write_text("old completed solver result")
    with pytest.raises(ValueError, match="result.json"):
        validate_clean_solver_artifacts(folder)


@pytest.mark.parametrize("bad", ["", "../" + RUN, "2"*31, "not-uuid", "b"*64])
def test_run_directory_never_accepts_unsafe_ids(bad, tmp_path):
    with pytest.raises(ValueError, match="ID"):
        validate_new_run(tmp_path, bad)


def test_original_step_cannot_be_deleted_by_mistaken_worker_argument(tmp_path):
    root = tmp_path / "scenario"
    root.mkdir()
    scope, owned, case, jobs, archive, verify, note = build_scope(root)
    protected = root / "actual_user_original.step"
    protected.write_bytes(b"THE USER'S ORIGINAL CAD FILE")
    scope["execute_fea"](RUN, UID, protected, case, {"sha256":CAD}, "ccx")
    assert protected.read_bytes() == b"THE USER'S ORIGINAL CAD FILE"
    assert jobs[RUN]["status"] == "failed"
    assert "result" not in jobs[RUN]
    assert all(stage != "fea_result" for stage,_ in archive)
    assert owned.read_bytes() == b"ONLY TEMPORARY COPIED STEP"


def test_run_scoped_temporary_step_is_only_unlink_target(tmp_path):
    root=tmp_path/"jobs"
    root.mkdir()
    owned=root/(RUN+".fea_input.step")
    owned.write_bytes(b"AUTHORIZED TEMPORARY")
    original=tmp_path/"source.step"
    original.write_bytes(b"USER ORIGINAL")
    assert owned_temporary_step(root,RUN,owned)
    assert not owned_temporary_step(root,RUN,original)
    assert not owned_temporary_step(root,"../bad",owned)
    assert not owned_temporary_step(root,RUN,root/(RUN+".fea_input.step.backup"))
    assert original.read_bytes()==b"USER ORIGINAL"


def test_stale_run_output_blocks_archive_even_if_fake_solver_would_succeed(tmp_path):
    root=tmp_path/"scenario"
    root.mkdir()
    scope, owned, case, jobs, archives, verify, note=build_scope(root)
    folder=root/"jobs"/"fea_runs"/RUN
    folder.mkdir(parents=True)
    stale=folder/"geofield_case.frd"
    stale.write_bytes(b"UNTRUSTED FRD OLD")
    scope["execute_fea"](RUN,UID,owned,case,{"sha256":CAD},"ccx")
    assert jobs[RUN]["status"]=="failed"
    assert "재사용" in jobs[RUN]["message"]
    assert stale.read_bytes()==b"UNTRUSTED FRD OLD"
    assert not owned.exists()
    assert all(stage!="fea_result" for stage,_ in archives)
    assert verify==[]


def test_worker_missing_refuses_success_or_fake_stage(tmp_path):
    root=tmp_path/"scenario"
    root.mkdir()
    scope, owned, case, tasks, archives, verify, notes=build_scope(root,worker=True)
    (root/"fea_engine_worker.py").unlink()
    scope["execute_fea"](RUN,UID,owned,case,{"sha256":CAD},"ccx")
    assert tasks[RUN]["status"]=="failed"
    assert "B01" in tasks[RUN]["message"]
    assert verify==[]
    assert all(kind!="fea_result" for kind,_ in archives)
    assert not owned.exists()


def test_worker_syntax_or_symlink_cannot_be_used_as_installed_source(tmp_path):
    script=tmp_path/"fea_engine_worker.py"
    script.write_text("def broken(:\n")
    assert not existing_worker_is_safe(tmp_path)
    script.write_text("def main(): return 1\n")
    assert existing_worker_is_safe(tmp_path)
    script.unlink()
    target=tmp_path/"original_user_step.step"
    target.write_bytes(b"PRIVACY")
    try:
        script.symlink_to(target)
    except (OSError,NotImplementedError):
        pytest.skip("Symlink creation is not available")
    assert not existing_worker_is_safe(tmp_path)
    assert target.read_bytes()==b"PRIVACY"


def test_owned_symlink_step_refused_without_unlinking_original(tmp_path):
    root=tmp_path/"scenario"
    root.mkdir()
    scope, owned, case, tasks, archives, verify, notes=build_scope(root)
    orig=root/"PROTECTED_STEP.step"
    orig.write_bytes(b"USER DATA")
    owned.unlink()
    try:
        owned.symlink_to(orig)
    except (OSError,NotImplementedError):
        pytest.skip("Symlink creation is not permitted")
    assert not owned_temporary_step(root/"jobs",RUN,owned)
    scope["execute_fea"](RUN,UID,owned,case,{"sha256":CAD},"ccx")
    assert tasks[RUN]["status"]=="failed"
    assert orig.read_bytes()==b"USER DATA"
    assert owned.is_symlink()


def test_solver_function_guards_residual_files_before_running_gmsh(tmp_path):
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
    fun=[node for node in tree.body if isinstance(node,ast.FunctionDef)
         and node.name=="run_real_fea"]
    assert len(fun)==1
    source=ast.get_source_segment(SOURCE.read_text(encoding="utf-8"),fun[0])
    assert source.index("validate_clean_solver_artifacts(workdir)") < source.index(
        "workdir.mkdir(parents=True,exist_ok=True)") < source.index("gmsh_mesh(")
    scope={"Path":Path}
    exec(compile(ast.Module(body=fun,type_ignores=[]),str(SOURCE),"exec"),scope)
    folder=tmp_path/"old_run"
    folder.mkdir()
    old=folder/"geofield_case.sta"
    old.write_bytes(b"OLD SUCCESS SUMMARY")
    with pytest.raises(ValueError,match="재사용"):
        scope["run_real_fea"](tmp_path/"source.step",{}, {},folder)
    assert old.read_bytes()==b"OLD SUCCESS SUMMARY"


def test_solver_worker_fails_explicitly_before_external_launch(tmp_path):
    root=tmp_path/"scenario"
    root.mkdir()
    scope, uploaded, case, tasks, archive, verify, notes=build_scope(root,worker=True)
    (root/"fea_engine_worker.py").write_bytes(b"\x00")
    scope["execute_fea"](RUN,UID,uploaded,case,{"sha256":CAD},"ccx")
    assert tasks[RUN]["status"]=="failed"
    assert "작업자 소스" in tasks[RUN]["message"]
    assert verify==[]
    assert all(k!="fea_result" for k,_ in archive)
